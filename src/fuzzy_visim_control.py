import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import win32com.client as com


# 1. časť - fuzzy systém
green = ctrl.Antecedent(np.arange(0, 31, 1), 'green')
red = ctrl.Antecedent(np.arange(0, 31, 1), 'red')
interval = ctrl.Consequent(np.arange(5, 31, 1), 'interval')

green['few'] = fuzz.trapmf(green.universe, [0, 0, 3, 9])
green['normal'] = fuzz.trimf(green.universe, [4, 11, 18])
green['a lot'] = fuzz.trimf(green.universe, [13, 20, 27])
green['very many'] = fuzz.trapmf(green.universe, [22, 27, 30, 30])

red['few'] = fuzz.trapmf(red.universe, [0, 0, 3, 9])
red['normal'] = fuzz.trimf(red.universe, [4, 11, 18])
red['a lot'] = fuzz.trimf(red.universe, [13, 20, 27])
red['very many'] = fuzz.trapmf(red.universe, [22, 27, 30, 30])

interval['short'] = fuzz.trapmf(interval.universe, [5, 5, 8, 12])
interval['normal'] = fuzz.trimf(interval.universe, [7, 13, 19])
interval['long'] = fuzz.trimf(interval.universe, [14, 20, 26])
interval['very long'] = fuzz.trapmf(interval.universe, [21, 26, 30, 30])

rules = [
    ctrl.Rule(green['few'] & red['few'], interval['short']),
    ctrl.Rule(green['few'] & red['normal'], interval['short']),
    ctrl.Rule(green['few'] & red['a lot'], interval['short']),
    ctrl.Rule(green['few'] & red['very many'], interval['short']),

    ctrl.Rule(green['normal'] & red['few'], interval['normal']),
    ctrl.Rule(green['normal'] & red['normal'], interval['normal']),
    ctrl.Rule(green['normal'] & red['a lot'], interval['normal']),
    ctrl.Rule(green['normal'] & red['very many'], interval['short']),

    ctrl.Rule(green['a lot'] & red['few'], interval['long']),
    ctrl.Rule(green['a lot'] & red['normal'], interval['long']),
    ctrl.Rule(green['a lot'] & red['a lot'], interval['normal']),
    ctrl.Rule(green['a lot'] & red['very many'], interval['normal']),

    ctrl.Rule(green['very many'] & red['few'], interval['very long']),
    ctrl.Rule(green['very many'] & red['normal'], interval['very long']),
    ctrl.Rule(green['very many'] & red['a lot'], interval['long']),
    ctrl.Rule(green['very many'] & red['very many'], interval['normal']),
]

fuzzy_sim = ctrl.ControlSystemSimulation(ctrl.ControlSystem(rules))

# výpočet dĺžky zelenej na základe počtu áut na zelenej + červenej
def fuzzy_dlzka_zelenej(auta_zelena, auta_cervena):
    # max do 30 áut
    fuzzy_sim.input['green'] = min(auta_zelena, 30)
    fuzzy_sim.input['red'] = min(auta_cervena, 30)
    fuzzy_sim.compute()
    return fuzzy_sim.output['interval']


# 2. časť - vissim
vissim = com.Dispatch("Vissim.Vissim.2026")
vissim.LoadNet(r"C:\Users\Public\Documents\PTV Vision\PTV Vissim 2026\Pezinok_fixed.inpx")

sim = vissim.Simulation
sim.SetAttValue("RandSeed", 42)
SIM_KONIEC = sim.AttValue("SimPeriod") # aktuálne 600s

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

# výpočet počtu čakajúcich aút pre každú cestu zvlášť
def pocet_cakajucich(linky):
    # zoberie vsetky auta v sieti: (cislo linky, rychlost v km/h)
    vozidla = vissim.Net.Vehicles.GetMultipleAttributes(("Lane\\Link\\No", "Speed"))
    pocet = 0
    for link, rychlost in vozidla:
        if int(link) in linky and rychlost < 5: # ak rýchlosť auta je menej ako 5km/h tak pravdepodobne čaká na červenej
            pocet += 1
    return pocet

# dĺžka simulácie
def bez_sekundy(sekundy):
    # simulacia bezi krok po kroku, kym neubehne dany cas
    koniec = sim.AttValue("SimSec") + sekundy
    while sim.AttValue("SimSec") < koniec and sim.AttValue("SimSec") < SIM_KONIEC - 1:
        sim.RunSingleStep()


# 3. časť - simulácie
sim.RunSingleStep()
nastav_semafory([1, 2, 3, 4, 5], "RED")

i = 0   # index aktualnej fazy
while sim.AttValue("SimSec") < SIM_KONIEC - 1:
    faza = FAZY[i]

    # spocitame auta vo vsetkych fazach
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

    dlzka = fuzzy_dlzka_zelenej(auta_zelena, auta_cervena)
    print(f"čas={sim.AttValue('SimSec'):.0f}s | faza SG{faza['sg']} | "
          f"čaká na zelenej: {auta_zelena}, max na červenej: {auta_cervena} -> dĺžka zelenej {dlzka:.1f} s")

    # dĺžka zelenej podľa výpočtu
    nastav_semafory(faza["sg"], "GREEN")
    bez_sekundy(dlzka)

    # oranžová 3s
    nastav_semafory(faza["sg"], "AMBER")
    bez_sekundy(3)

    # červená 2s
    nastav_semafory(faza["sg"], "RED")
    bez_sekundy(2)

    # ďalšia fáza
    i = (i + 1) % len(FAZY)

sim.Stop()