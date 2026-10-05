import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

#napr. vstup green = 14 a red = 17

#vstupný počet áut od 0 po 30
#výstupný interval min. 5 sec
green = ctrl.Antecedent(np.arange(0, 31, 1), 'green')
red = ctrl.Antecedent(np.arange(0, 31, 1), 'red')
interval = ctrl.Consequent(np.arange(5, 31, 1), 'interval')


#membership funkcie: trimf - trojuholnik, trapmf - lichobeznik
#vlavo: (x-a)/(b-a)
#vpravo: (c-x)/(c-b)
green['few'] = fuzz.trapmf(green.universe, [0, 0, 3, 9])
green['normal'] = fuzz.trimf(green.universe, [4, 11, 18]) #(18-14)/(18-11) = 4/7 = 0.571
green['a lot'] = fuzz.trimf(green.universe, [13, 20, 27]) #(14-13)/(20-13) = 1/7 = 0.143
green['very many'] = fuzz.trapmf(green.universe, [22, 27, 30, 30])

red['few'] = fuzz.trapmf(red.universe, [0, 0, 3, 9])
red['normal'] = fuzz.trimf(red.universe, [4, 11, 18]) #(18-17)/(18-11) = 1/7 = 0.143
red['a lot'] = fuzz.trimf(red.universe, [13, 20, 27]) #(17-13)/(20-13) = 4/7 = 0.571
red['very many'] = fuzz.trapmf(red.universe, [22, 27, 30, 30])

interval['short'] = fuzz.trapmf(interval.universe, [5, 5, 8, 12])
interval['normal'] = fuzz.trimf(interval.universe, [7, 13, 19])
interval['long'] = fuzz.trimf(interval.universe, [14, 20, 26])
interval['very long'] = fuzz.trapmf(interval.universe, [21, 26, 30, 30])


#pravidlá - pomocou min pravidla
rules = [
    ctrl.Rule(green['few'] & red['few'], interval['short']),
    ctrl.Rule(green['few'] & red['normal'], interval['normal']),
    ctrl.Rule(green['few'] & red['a lot'], interval['long']),
    ctrl.Rule(green['few'] & red['very many'], interval['short']),

    ctrl.Rule(green['normal'] & red['few'], interval['normal']),
    ctrl.Rule(green['normal'] & red['normal'], interval['normal']), #min(0.571; 0.143) = 0.143
    ctrl.Rule(green['normal'] & red['a lot'], interval['normal']), #min(0.571; 0.571) = 0.571
    ctrl.Rule(green['normal'] & red['very many'], interval['short']),

    ctrl.Rule(green['a lot'] & red['few'], interval['long']),
    ctrl.Rule(green['a lot'] & red['normal'], interval['long']), #min(0.143; 0.143) = 0.143
    ctrl.Rule(green['a lot'] & red['a lot'], interval['normal']), #min(0.143; 0.571) = 0.143
    ctrl.Rule(green['a lot'] & red['very many'], interval['normal']),

    ctrl.Rule(green['very many'] & red['few'], interval['very long']),
    ctrl.Rule(green['very many'] & red['normal'], interval['very long']),
    ctrl.Rule(green['very many'] & red['a lot'], interval['long']),
    ctrl.Rule(green['very many'] & red['very many'], interval['normal']),
]
#z každej množiny len to najsilnejšie cez max
#normal = max(0.143; 0.571; 0.143) = 0.571
#long = max(0.143) = 0.143

#poskladanie pravidiel + vytvorenie "objektu"
interval_ctrl = ctrl.ControlSystem(rules)
sim = ctrl.ControlSystemSimulation(interval_ctrl)


#počet áut na semaforoch
sim.input['green'] = 14
sim.input['red'] = 17
sim.compute() #defuzzifikácia - pomocou centroidu - taziska
#ako vážený priemer (sum( x * výška v x))/(sum ( výška v x))

print(f"Odporúčaná dĺžka zelenej je: {sim.output['interval']:.2f} s")


#graf
interval.view(sim=sim)