import uuid
import datetime
import urllib.request
from bs4 import BeautifulSoup
import pickle
import pathlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

pVPowerPlants = [
    {'url': 'https://pvoutput.org/intraday.jsp?id=31472&sid=28833&dt=20200704&gs=0&m=0'},   # Australia/Sydney power plant 1
    {'url': 'https://pvoutput.org/intraday.jsp?id=83097&sid=73671&dt=20200704&gs=0&m=0'},   # Australia/Sydney power plant 2
    # {'url': 'https://pvoutput.org/intraday.jsp?id=79505&sid=70501&dt=20200703&gs=0&m=0'},   # Australia/Brisbane
]

pVPowerPlantsPickleFile = pathlib.Path('pv-power-plants.pickle')
if (pVPowerPlantsPickleFile.exists()):
    with open(pVPowerPlantsPickleFile, 'rb') as f:
        pVPowerPlants = pickle.load(f)
else:
    for powerPlantIdx, powerPlant in enumerate(pVPowerPlants):
        print(powerPlant['url'])
        with urllib.request.urlopen(powerPlant['url']) as response:
            jsScript = BeautifulSoup(response.read()).findAll('script')[-2].string
            powerPlant = {}
            for jsScriptLine in jsScript.split(';'):
                jsScriptLine = jsScriptLine.strip()
                if 'var systemName = ' in jsScriptLine:
                    powerPlant['powerPlantName'] = jsScriptLine.split(' = ')[1].replace('\'', '')
                elif 'var timezone = ' in jsScriptLine:
                    powerPlant['timeZone'] = jsScriptLine.split(' = ')[1].replace('\'', '')
                elif 'var lng = ' in jsScriptLine:
                    powerPlant['lng'] = float(jsScriptLine.split(' = ')[1])
                elif 'var lat = ' in jsScriptLine:
                    powerPlant['lat'] = float(jsScriptLine.split(' = ')[1])
                elif 'var cats = ' in jsScriptLine:
                    powerPlant['localTime'] = jsScriptLine.split('[')[1].split(']')[0].replace('\'', '').split(',')
                elif 'var dataPowerOut = ' in jsScriptLine:
                    powerPlant['powerOutput'] = [int(str) for str in jsScriptLine.split('[')[1].split(']')[0].replace('\'', '').split(',')]
            pVPowerPlants[powerPlantIdx] = powerPlant
    pickle.dump(pVPowerPlants, open(pVPowerPlantsPickleFile, 'wb'))

aggregatedPowerSupply = {}
for hour in range(6, 12 + 6):
    for minute in range(0, 60, 5):
        time = datetime.datetime(year=2020, month=7, day=3, hour=hour, minute=minute)
        aggregatedPowerSupply[time] = 0

for powerPlantIdx, powerPlant in enumerate(pVPowerPlants):
    for time, powerOutput in zip(powerPlant['localTime'], powerPlant['powerOutput']):
        if powerOutput == 0:
            continue
        hour, minute = [int(timeToken) for timeToken in time[:-2].split(':')]
        meridiem = time[-2:]
        if meridiem == 'PM' and hour != 12:
            hour += 12
        time = datetime.datetime(year=2020, month=7, day=3, hour=hour, minute=minute)
        try:
            aggregatedPowerSupply[time] += powerOutput
        except KeyError:
            aggregatedPowerSupply[time] = powerOutput

powerSupplyCurve = []
for time, powerOutput in aggregatedPowerSupply.items():
    powerSupplyCurve.append({'time': time, 'powerOutput': powerOutput})
powerSupplyCurve.sort(key=lambda supply:supply['time'], reverse=False)   # Sort ascending time


# Super Simple Dataset
powerDemands = []
for _ in range(5):
    powerDemands.append({
        'id': uuid.uuid4(),
        'currentCapacityWatt': 15 * 1000,   # 15KW
        'maxCapacityWatt': 50 * 1000,   # 50KW
        'minTargetCapacityWatt': 30 * 1000,
        'consumptionRate': 120 * 10,   # Constant Usage for now (Whr)
    })
    powerDemands.append({
        'id': uuid.uuid4(),
        'currentCapacityWatt': 20 * 1000,   # 15KW
        'maxCapacityWatt': 75 * 1000,   # 50KW
        'minTargetCapacityWatt': 30 * 1000,
        'consumptionRate': 120 * 15,   # Constant Usage
    })
    powerDemands.append({
        'id': uuid.uuid4(),
        'currentCapacityWatt': 25 * 1000,   # 15KW
        'maxCapacityWatt': 100 * 1000,   # 50KW
        'minTargetCapacityWatt': 30 * 1000,
        'consumptionRate': 120 * 15,   # Constant Usage
    })



# Greedy Power Demand Scheduler
for powerSupplyInstantIdx, powerSupplyInstant in enumerate(powerSupplyCurve):
    powerSupplyInstant['fulfilledDemand'] = 0
    powerSupplyInstant['fulfilledCriticalDemandId'] = []
    powerSupplyInstant['fulfilledNonCriticalDemandId'] = []
    # Populate critical power demand first
    for powerDemandIdx, powerDemand in enumerate(powerDemands):
        criticalPowerDemand = powerDemand['currentCapacityWatt'] - powerDemand['minTargetCapacityWatt']
        if criticalPowerDemand > 0:
            continue   # no critical power demand
        if powerDemand['consumptionRate'] <= powerSupplyInstant['powerOutput'] - powerSupplyInstant['fulfilledDemand']:
            powerSupplyInstant['fulfilledDemand'] += powerDemand['consumptionRate']
            powerSupplyInstant['fulfilledCriticalDemandId'].append(powerDemand['id'])
            try:
                powerDemand['consumption'].append({'time': powerSupplyInstant['time'], 'consumed': powerDemand['consumptionRate']})
            except KeyError:
                powerDemand['consumption'] = [{'time': powerSupplyInstant['time'], 'consumed': powerDemand['consumptionRate']}]
            powerDemand['currentCapacityWatt'] += powerDemand['consumptionRate']
            powerDemands[powerDemandIdx] = powerDemand
    # Populate non-critical power demand
    for powerDemandIdx, powerDemand in enumerate(powerDemands):
        if powerDemand['id'] in powerSupplyInstant['fulfilledCriticalDemandId']:
            continue   # demand has already been fulfilled
        noncriticalPowerDemand = powerDemand['maxCapacityWatt'] - powerDemand['currentCapacityWatt']
        if noncriticalPowerDemand <= 0:
            continue   # no power demand
        if noncriticalPowerDemand > powerDemand['consumptionRate']:
            noncriticalPowerDemand = powerDemand['consumptionRate']   # limit demand to consumption rate

        if noncriticalPowerDemand <= powerSupplyInstant['powerOutput'] - powerSupplyInstant['fulfilledDemand']:
            powerSupplyInstant['fulfilledDemand'] += noncriticalPowerDemand
            powerSupplyInstant['fulfilledNonCriticalDemandId'].append(powerDemand['id'])
            try:
                powerDemand['consumption'].append({'time': powerSupplyInstant['time'], 'consumed': noncriticalPowerDemand})
            except KeyError:
                powerDemand['consumption'] = [{'time': powerSupplyInstant['time'], 'consumed': noncriticalPowerDemand}]
            powerDemand['currentCapacityWatt'] += noncriticalPowerDemand
            powerDemands[powerDemandIdx] = powerDemand
    powerSupplyCurve[powerSupplyInstantIdx] = powerSupplyInstant

# Plot supply and demand
plt.figure(figsize=(10, 2.5))
dates = mdates.date2num([supply['time'] for supply in powerSupplyCurve])
plt.plot_date(dates, [supply['powerOutput'] for supply in powerSupplyCurve],
              lineStyle='-', drawstyle='steps-post', label="power generation capacity")
plt.plot_date(dates, [supply['fulfilledDemand'] for supply in powerSupplyCurve],
              lineStyle='-', drawstyle='steps-post', label="adjusted demand")

plt.gcf().autofmt_xdate()
myFmt = mdates.DateFormatter('%B %m, %Y %I:%M%p')
plt.gca().xaxis.set_major_formatter(myFmt)
plt.legend()

plt.show()