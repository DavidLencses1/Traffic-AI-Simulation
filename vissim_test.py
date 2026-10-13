import win32com.client as com

#spustíme cez vissim
vissim = com.Dispatch("Vissim.Vissim.2026")

#súbor s križovatkou
vissim.LoadNet(r"C:\Users\Public\Documents\PTV Vision\PTV Vissim 2026\test.inpx")

sim = vissim.Simulation
sim.SetAttValue("RandSeed", 42)
sim.SetAttValue("SimRes", 5)
sim.SetAttValue("UseMaxSimSpeed", True)
total = 0

for step in range(3000):
    sim.RunSingleStep()
    vehicles = vissim.Net.Vehicles
    if vehicles.Count > 0:
        total = max(total, max(v[1] for v in vehicles.GetMultiAttValues("No")))

sim.Stop()
print("Celkovo aut:", total)