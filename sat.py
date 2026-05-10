import sys
import math
import requests
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QTimer, QObject, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QColor

from skyfield.api import load, EarthSatellite

# ================= CONFIG =================

TLE_URLS = {
    "GPS": "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle",
    "GLONASS": "https://celestrak.org/NORAD/elements/gp.php?GROUP=glo-ops&FORMAT=tle",
    "GALILEO": "https://celestrak.org/NORAD/elements/gp.php?GROUP=galileo&FORMAT=tle",
    "BEIDOU": "https://celestrak.org/NORAD/elements/gp.php?GROUP=beidou&FORMAT=tle"
}
UPDATE_MS = 1000
TRAIL_LEN = 40

ts = load.timescale()

# ================= BRIDGE =================

class Bridge(QObject):

    def __init__(self, radar):
        super().__init__()
        self.radar = radar

    @pyqtSlot(str)
    def sat_clicked(self, name):

        if name not in self.radar.sat_data:
            return

        s = self.radar.sat_data[name]

        info = (
            f"SATELLITE: {name}\n"
            f"CONSTELLATION: {s['constellation']}\n"
            f"NORAD: {s['norad']}\n\n"
            f"LAT: {s['lat']:.6f}°\n"
            f"LON: {s['lon']:.6f}°\n"
            f"ALT: {s['alt']:.3f} km\n\n"
            f"SPEED: {s['speed']:.4f} km/s\n"
            f"SPEED: {s['speed']*3600:.0f} km/h\n\n"
            f"INCLINATION: {s['inc']:.3f}°\n"
            f"PERIOD: {s['period']:.2f} min\n\n"
            f"UTC: {datetime.utcnow().strftime('%H:%M:%S')}"
        )

        self.radar.show_info(info)

# ================= RADAR =================

class Radar(QMainWindow):

    def __init__(self):

        super().__init__()

        self.resize(1400, 900)
        self.setWindowTitle("Satellite Radar")

        self.browser = QWebEngineView()

        self.browser.setStyleSheet("background:black")
        self.browser.page().setBackgroundColor(QColor("black"))

        self.setCentralWidget(self.browser)

        self.channel = QWebChannel()
        self.bridge = Bridge(self)

        self.channel.registerObject("bridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)

        self.sats = []
        self.sat_data = {}
        self.trails = {}

        self.load_sats()
        self.load_map()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_satellites)
        self.timer.start(UPDATE_MS)

    # ================= LOAD SAT =================

    def load_sats(self):

        for const, url in TLE_URLS.items():

            try:

                print(f"Loading {const} satellites...")

                response = requests.get(url, timeout=10)
                response.raise_for_status()

                lines = response.text.strip().splitlines()

                # remove empty lines
                lines = [line.strip() for line in lines if line.strip()]

                loaded = 0

                for i in range(0, len(lines), 3):

                    # avoid IndexError
                    if i + 2 >= len(lines):
                        print(f"Incomplete TLE skipped in {const}")
                        continue

                    name = lines[i]
                    l1 = lines[i + 1]
                    l2 = lines[i + 2]

                    # validate TLE
                    if not l1.startswith("1 ") or not l2.startswith("2 "):
                        print(f"Invalid TLE skipped: {name}")
                        continue

                    try:

                        sat = EarthSatellite(l1, l2, name, ts)

                        self.sats.append({
                            "obj": sat,
                            "name": name,
                            "const": const,
                            "norad": l1[2:7]
                        })

                        self.trails[name] = []

                        loaded += 1

                    except Exception as e:
                        print(f"Satellite parse error: {name} -> {e}")

                print(f"{const}: {loaded} satellites loaded")

            except Exception as e:
                print(f"Error loading {const}: {e}")

    # ================= MAP =================

    def load_map(self):

        html = """
<!DOCTYPE html>
<html>

<head>

<meta charset="utf-8"/>

<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>

<style>

html, body {

background:black;
margin:0;
padding:0;
height:100%;
width:100%;
overflow:hidden;

}

#map {

position:fixed;
top:0;
left:0;
width:100%;
height:100%;

}

#infoBox {

position:fixed;

bottom:20px;
right:20px;

width:340px;
min-height:200px;

background:rgba(0,0,0,0.95);

border:1px solid aqua;

color:white;

padding:12px;

font-family:Consolas;
font-size:13px;

white-space:pre;

z-index:999999;

}

.sat-label {

color:white;
font-family:Consolas;
font-size:12px;
font-weight:bold;

text-shadow:
0 0 5px black,
0 0 8px black;

background:none;
border:none;

}

</style>

</head>

<body>

<div id="map"></div>

<div id="infoBox">
CLICK SATELLITE
</div>

<script>

var map = L.map("map",{
zoomControl:false,
attributionControl:false
}).setView([20,0],2);

L.tileLayer(
'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
{
subdomains:'abcd'
}
).addTo(map);

var sats={}
var trails={}

new QWebChannel(qt.webChannelTransport,function(channel){

window.bridge=channel.objects.bridge

})

function update_sat(name,lat,lon,trail){

var icon=L.divIcon({
html:'<div style="width:12px;height:12px;background:aqua;border-radius:50%"></div>',
iconSize:[12,12]
})

if(!sats[name]){

var marker=L.marker([lat,lon],{icon:icon}).addTo(map)

marker.bindTooltip(name,{
permanent:true,
direction:"right",
className:"sat-label",
offset:[10,0]
})

marker.on("click",function(){

bridge.sat_clicked(name)

})

sats[name]=marker

}else{

sats[name].setLatLng([lat,lon])

}

if(trails[name]){

map.removeLayer(trails[name])

}

trails[name]=L.polyline(trail,{
color:"lime",
weight:2
}).addTo(map)

}

function show_info(text){

document.getElementById("infoBox").innerText=text

}

</script>

</body>
</html>
"""

        self.browser.setHtml(html)

    # ================= UPDATE =================

    def update_satellites(self):

        t = ts.now()

        for s in self.sats:

            try:

                sat = s["obj"]
                name = s["name"]

                geo = sat.at(t).subpoint()

                lat = geo.latitude.degrees
                lon = geo.longitude.degrees
                alt = geo.elevation.km

                vel = sat.at(t).velocity.km_per_s
                speed = math.sqrt(sum(v*v for v in vel))

                inc = sat.model.inclo * 180 / math.pi
                period = 1440 / sat.model.no_kozai

                self.trails[name].append([lat, lon])

                if len(self.trails[name]) > TRAIL_LEN:
                    self.trails[name].pop(0)

                self.sat_data[name] = {

                    "lat": lat,
                    "lon": lon,
                    "alt": alt,
                    "speed": speed,
                    "inc": inc,
                    "period": period,
                    "constellation": s["const"],
                    "norad": s["norad"]

                }

                js = f'update_sat("{name}", {lat}, {lon}, {self.trails[name]});'

                self.browser.page().runJavaScript(js)

            except Exception as e:
                print(f"Update error for {name}: {e}")

    # ================= INFO =================

    def show_info(self, text):

        escaped = text.replace("`", "\\`")

        js = f"show_info(`{escaped}`);"

        self.browser.page().runJavaScript(js)

# ================= RUN =================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    win = Radar()
    win.show()

    sys.exit(app.exec())