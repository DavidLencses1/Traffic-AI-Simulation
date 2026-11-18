import random
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import win32com.client as com
import matplotlib.pyplot as plt

# 1. časť - vissim
vissim = com.Dispatch("Vissim.Vissim.2026")
vissim.LoadNet(r"C:\Users\Public\Documents\PTV Vision\PTV Vissim 2026\Pezinok_fixed.inpx")

sim = vissim.Simulation
sim.SetAttValue("RandSeed", 42)
sim.SetAttValue("SimPeriod", 500) # 500s simulácie
sim.SetAttValue("SimRes", 5)
sim.SetAttValue("UseMaxSimSpeed", True)
SIM_KONIEC = sim.AttValue("SimPeriod")

# vypne grafiku vo vissime
vissim.Graphics.CurrentNetworkWindow.SetAttValue("QuickMode", 1)

# prvých 120s nerátame, nech sa križovatka zaplní
vissim.Evaluation.SetAttValue("VehNetPerfCollectData", True)
vissim.Evaluation.SetAttValue("VehNetPerfFromTime", 120)

# controller križovatky
sc = vissim.Net.SignalControllers.ItemByKey(1)

# ktoré semafory majú spolu zelenú + na akých cestách čakajú ich autá
FAZY = [
    {"sg": [1, 2], "linky": [6, 7, 10000]},
    {"sg": [4, 5], "linky": [5, 10004, 1]},
    {"sg": [3],    "linky": [2, 10001]},
]

# nastavenie farby na semafore
def nastav_semafory(cisla_sg, stav):
    # stav = RED/GREEN/AMBER
    for cislo in cisla_sg:
        sc.SGs.ItemByKey(cislo).SetAttValue("SigState", stav)


# výpočet počtu čakajúcich áut pre každú cestu zvlášť
def pocet_cakajucich(linky):
    # zoberie vsetky auta v sieti: (cislo linky, rychlost v km/h)
    vozidla = vissim.Net.Vehicles.GetMultipleAttributes(("Lane\\Link\\No", "Speed"))
    pocet = 0
    for link, rychlost in vozidla:
        if int(link) in linky and rychlost < 5:
            pocet += 1
    return pocet


# dĺžka simulácie
def bez_sekundy(sekundy):
    teraz = sim.AttValue("SimSec")
    koniec = min(teraz + sekundy, SIM_KONIEC - 1)
    if koniec <= teraz:
        return
    sim.SetAttValue("SimBreakAt", koniec)
    sim.RunContinuous()

# 2. časť - fuzzy systém z jedinca
MAX_AUT = 35
INPUT_NAMES = ['few', 'normal', 'a lot', 'very many']
OUTPUT_NAMES = ['short', 'normal', 'long', 'very long']

# 3 bity prevedieme na číslo: 0 - 7
# ktoré určujú kde začína ďalší bod membership funkcie
def bits_to_int(gene):
    return gene[0]*4 + gene[1]*2 + gene[2]

# 4 gény => 4 body membership funkcie
def decode_points(genes, start):
    points = []

    # 1. bod membership funkcie
    point = start + bits_to_int(genes[0])
    points.append(point)

    # ďalšie body = predchádzajúci bod + medzera + 1 (ak by gene bol 0)
    for gene in genes[1:]:
        point = point + bits_to_int(gene) + 1
        points.append(point)

    return points

# celý jedinec => body pre green, red, interval
def decode_individual(individual):
    green_points = decode_points(individual[0:4], 0) # max 31 áut = 7 + 8 + 8 + 8
    red_points = decode_points(individual[4:8], 0) # max 31 áut = 7 + 8 + 8 + 8
    interval_points = decode_points(individual[8:12], 5) # max 36s = 5 + 7 + 8 + 8 + 8
    return green_points, red_points, interval_points

# gény 12-27 => výstupy 16 pravidiel
def decode_rules(individual):
    outputs = []
    for gene in individual[12:28]:
        index = bits_to_int(gene) % 4 # 0-7 prevedieme na 0-3 (short - 0, normal - 1, long - 2, very long - 3)
        outputs.append(OUTPUT_NAMES[index])
    return outputs

# 4 body => 4 membership funkcie
def set_membership(variable, points, names, minimum, maximum):
    p1, p2, p3, p4 = points
    variable[names[0]] = fuzz.trapmf(variable.universe, [minimum, minimum, p1, p2])
    variable[names[1]] = fuzz.trimf(variable.universe, [p1, p2, p3])
    variable[names[2]] = fuzz.trimf(variable.universe, [p2, p3, p4])
    variable[names[3]] = fuzz.trapmf(variable.universe, [p3, p4, maximum, maximum])

# z jedinca postavíme fuzzy systém
def build_fuzzy(individual):
    green_points, red_points, interval_points = decode_individual(individual)

    green = ctrl.Antecedent(np.arange(0, MAX_AUT + 1, 1), 'green')
    red = ctrl.Antecedent(np.arange(0, MAX_AUT + 1, 1), 'red')
    interval = ctrl.Consequent(np.arange(5, 37, 1), 'interval')

    set_membership(green, green_points, INPUT_NAMES, 0, MAX_AUT)
    set_membership(red, red_points, INPUT_NAMES, 0, MAX_AUT)
    set_membership(interval, interval_points, OUTPUT_NAMES, 5, 36)

    # pravidlá fuzzy systému => trz hľadáme cez genetický algoritmus
    rule_outputs = decode_rules(individual)

    # pravidlá fuzzy systému
    rules = []
    k = 0
    for g in INPUT_NAMES:  # green: few, normal, a lot, very many
        for r in INPUT_NAMES:  # red: few, normal, a lot, very many
            rules.append(ctrl.Rule(green[g] & red[r], interval[rule_outputs[k]]))
            k += 1

    return ctrl.ControlSystemSimulation(ctrl.ControlSystem(rules))

# výpočet dĺžky zelenej pre daný fuzzy systém
def fuzzy_dlzka_zelenej(fuzzy_sim, auta_zelena, auta_cervena):
    fuzzy_sim.input['green'] = min(auta_zelena, MAX_AUT)
    fuzzy_sim.input['red'] = min(auta_cervena, MAX_AUT)
    fuzzy_sim.compute()
    return fuzzy_sim.output['interval']

# 3. časť - fitness funkcia
def run_simulation(fuzzy_sim):
    sim.RunSingleStep()
    nastav_semafory([1, 2, 3, 4, 5], "RED")

    i = 0
    while sim.AttValue("SimSec") < SIM_KONIEC - 1:
        # spočítame autá vo všetkých fázach
        pocty = []
        for f in FAZY:
            pocet = pocet_cakajucich(f["linky"])
            pocty.append(pocet)

        # počet áut vo fáze, ktorá dostane zelenú
        auta_zelena = pocty[i]

        # max počet aút na červenej okrem fázy, ktorá ide dostať zelenú
        auta_cervena = 0
        for j in range(len(FAZY)):
            if j == i: # aktuálna fáza => preskakujeme
                continue
            if pocty[j] > auta_cervena:
                auta_cervena = pocty[j]

        dlzka = fuzzy_dlzka_zelenej(fuzzy_sim, auta_zelena, auta_cervena)

        # dĺžka zelenej podľa výpočtu
        nastav_semafory(FAZY[i]["sg"], "GREEN")
        bez_sekundy(dlzka)

        # oranžova 3s
        nastav_semafory(FAZY[i]["sg"], "AMBER")
        bez_sekundy(3)

        # červená 2s
        nastav_semafory(FAZY[i]["sg"], "RED")
        bez_sekundy(2)

        # ďalšia fáza
        i = (i + 1) % len(FAZY)

    sim.SetAttValue("SimBreakAt", 0)
    sim.RunContinuous()

    # priemerné zdržanie vozidla je vstupom pre fitness funkciu
    zdrzanie = vissim.Net.VehicleNetworkPerformanceMeasurement.AttValue("DelayAvg(Current, Total, All)")
    return zdrzanie

# vyhodnotíme jednotlivca v generácii
def evaluate_individual(individual):
    fuzzy_sim = build_fuzzy(individual)
    return run_simulation(fuzzy_sim)

# 4. časť - genetický algoritmus

# vytvoríme nahodný gén pomocou náhodných bitov
def random_gene(gene_length):
    gene = []
    for i in range(gene_length):
        gene.append(random.randrange(0, 2))
    return gene

# poskládame jednotlivca z vytvorených génov
def random_individual(num_genes, gene_length):
    individual = []
    for i in range(num_genes):
        individual.append(random_gene(gene_length))
    return individual

# vyberieme elitných jedincov, ktorí majú najmenšie zdržanie
def elite_selection(population, fitness, num_of_elites):
    temp_fitness = fitness[:]
    new_population = []
    elite_indexes = []

    for i in range(num_of_elites):
        best_index = 0
        best_fit = float("inf")

        for j in range(len(temp_fitness)):
            if temp_fitness[j] < best_fit:
                best_fit = temp_fitness[j]
                best_index = j

        elite_clone = [gene[:] for gene in population[best_index]]
        new_population.append(elite_clone)

        # zabezpečíme, že ho nevyberieme 2x
        temp_fitness[best_index] = float("inf")
        elite_indexes.append(best_index)

    return new_population, elite_indexes

# turnajový výber
def tournament(population, fitness, elite_indexes):
    tournament_winners = []

    num_of_tournaments = len(population) - len(elite_indexes)

    # elitných jedincov do turnaja neberieme
    temp_population = []
    for i in range(len(population)):
        if i not in elite_indexes:
            temp_population.append(i)

    for i in range(num_of_tournaments):
        player1 = random.choice(temp_population)
        player2 = random.choice(temp_population)

        # hľadáme 2 rozdielnych jedincov
        while player1 == player2:
            player2 = random.choice(temp_population)

        # vyberieme toho s menšim zdražaním
        if fitness[player1] <= fitness[player2]:
            tournament_winners.append(player1)
        else:
            tournament_winners.append(player2)

    return tournament_winners, num_of_tournaments

# kríženie
def cross_over(tournaments, population):
    index1 = random.choice(tournaments)
    index2 = random.choice(tournaments)

    # skusíme iba 10x nájsť iného rodiča => ak máme málo jedincov v populácii
    pokusy = 0
    while index1 == index2 and pokusy < 10:
        index2 = random.choice(tournaments)
        pokusy += 1

    parent1 = population[index1]
    parent2 = population[index2]

    # one-point cross-over
    cross_over_point = random.randint(1, len(parent1) - 1)
    left1 = [gene[:] for gene in parent1[:cross_over_point]]
    right1 = [gene[:] for gene in parent1[cross_over_point:]]
    left2 = [gene[:] for gene in parent2[:cross_over_point]]
    right2 = [gene[:] for gene in parent2[cross_over_point:]]

    child1 = left1 + right2
    child2 = left2 + right1

    return child1, child2


# bit-flip mutácia (bez elít)
def mutate(new_generation, num_of_elites, mutation_rate):
    for individual in new_generation[num_of_elites:]:
        for gene in individual:
            for bit in range(len(gene)):
                if random.random() < mutation_rate:
                    if gene[bit] == 1:
                        gene[bit] = 0
                    else:
                        gene[bit] = 1

    return new_generation

def main():

    # nastavenie parametrov
    num_genes = 28 # pre každu premennú 4 gény = 4 body + 16 génov pre pravidlá
    gene_length = 3 # 3 bity na jeden bod v membership funkcii
    population_size = 30 # veľkosť populácie
    max_generations = 500 # počet generácií
    num_of_elites = 2 # počet elitných jedincov
    num_of_new = 5 # počet nových jedincov v každej generácii
    mutation_rate = 0.05 # miera mutácia

    # cache pamäť pre jedincov, ktorých sme počítali
    cache = {}

    best_fitness = []
    avg_fitness = []

    best_individual = None
    best_value = float("inf")

    # prvú generáciu zvolíme náhodne
    population = []
    for i in range(population_size):
        population.append(random_individual(num_genes, gene_length))

    # cyklus genetického algoritmu
    for generation in range(max_generations):

        fitness = []

        # vypočítame fitness každého jedinca
        for i in range(population_size):
            key = str(population[i]) # jedinec bude kľučom
            if key in cache:
                value = cache[key] # tohto jedinca sme už simulovali
            else:
                value = evaluate_individual(population[i])
                cache[key] = value
            fitness.append(value)
            print(f"  jedinec {i + 1:02d}/{population_size}: zdržanie {value:.2f} s")

            # zachováme si toho najlepšieho
            if value < best_value:
                best_value = value
                best_individual = [gene[:] for gene in population[i]]

        # pre každú generáciu vypočítame:
        best = min(fitness)
        avg = sum(fitness) / len(fitness)
        best_fitness.append(best)
        avg_fitness.append(avg)
        print(f"Generation {generation + 1:03d}")
        print(f"Best fitness: {best:.2f} s")
        print(f"Avg. fitness: {avg:.2f} s")
        print("-----------------------------------------------")

        # vytvoríme novú generáciu
        new_generation = []

        # vyberieme elitných jedincov
        elites, elite_indexes = elite_selection(population, fitness, num_of_elites)

        # turnajový výber z ostatných jedincov
        tournaments, number_of_tournaments = tournament(population, fitness, elite_indexes)

        # do novej generácie sa elitní jedinci dostanú ako prvý
        for x in elites:
            new_generation.append(x)

        # križenie kým máme miesto aj pre nových jedincov
        while len(new_generation) < population_size - num_of_new:
            child1, child2 = cross_over(tournaments, population)
            new_generation.append(child1)
            if len(new_generation) < population_size - num_of_new:
                new_generation.append(child2)

        # mutácia bez elít
        new_generation = mutate(new_generation, num_of_elites, mutation_rate)

        # vytvorenie nových náhodných jedincov
        for i in range(num_of_new):
            new_generation.append(random_individual(num_genes, gene_length))

        # nová generácia sa stane súčastnou generáciu
        population = new_generation

    # najlepšie riešenie, ktoré sme našli
    green_points, red_points, interval_points = decode_individual(best_individual)
    print("Best solution:")
    print(f"Zdržanie: {best_value:.2f} s")
    print(f"green body: {[round(num, 2) for num in green_points]}")
    print(f"red body: {[round(num, 2) for num in red_points]}")
    print(f"interval body: {[round(num, 2) for num in interval_points]}")

    print("Pravidlá:")
    rule_outputs = decode_rules(best_individual)
    k = 0
    for g in INPUT_NAMES:
        for r in INPUT_NAMES:
            print(f"  green {g} & red {r} -> {rule_outputs[k]}")
            k += 1

    # výsledný graf fitness funkcie
    generacie = range(1, len(best_fitness) + 1)
    plt.plot(generacie, best_fitness, label="Best")
    plt.plot(generacie, avg_fitness, label="Average")
    plt.legend()
    plt.xlabel("Generácia")
    plt.ylabel("Priemerné zdržanie [s]")
    plt.grid(True)
    plt.show()


if __name__ == '__main__':
    main()

'''
jedinec = 28 génov
gén = 3 bity
-gény 0-3 => 4 body pre green membership funkciu
-gény 4-7 => 4 body pre red membership funkciu
-gény 8-11 => 4 body pre výsledný interval membreship funkciu

gény (v bitoch) prevedieme na čísla, napr.
-[1,1,1] = 7
-[0,0,1] = 1
-[0,0,1] = 1
-[1,1,1] = 7

z čísiel, ktoré sme dostali z génov poskládame body pre membership funkciu:
p1 => 7 = 7
p2 => 9 = 7 + 1 + 1
p3 => 11 = 9 + 1 + 1
p4 => 19 = 11 + 7 + 1

poskladáme membership funkciu:
few = [min, min, p1, p2]
normal = [p1, p2, p3]
a lot = [p2, p3, p4]
very many  = [p3, p4, max, max]

čize pre 7,9,11,19:
few = [0, 0, 7, 9]
normal = [7, 9, 11]
a lot = [9, 11, 19]
very many = [11, 19, 35, 35]

gény 12-27 sú pravidlá fuzzy systému
gén (3 bity) => číslo 0-7 => číslo % 4 => výsledné pravidlo (0 - short, 1 - normal, 2 - long, 3 - very long)
'''