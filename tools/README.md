# TessyNav analysis tools

Scripts Claude uses to check drives. No passwords or keys are stored here.

Setup (in an empty folder):
1. `git clone --depth 1 https://github.com/Tessynav/tessynav.github.io.git site` (the app's code, read by the replays)
2. Copy this `tools` folder next to it.
3. Download a trip from tessynav-trips and decrypt it: `python3 tools/dec.py trip.json '<trip password>' trip_dec.json`
4. Road data for the replay: `sh tools/get_packs.sh trip_dec.json` (from the `tiles` branch of this repository)

Checks:
- `python3 tools/rec_report.py trip_dec.json`: frame rate, drawing load, sideways weave, notes
- `TRACK=site/v2/js/track.js TRIP=trip_dec.json A=<start s> B=<end s> node tools/hwtest2b.js`: car vs GPS accuracy
- `TRACK=site/v2/js/track.js TRIP=trip_dec.json A=.. B=.. node tools/worldlat2.js`: weave in a replay
- `APP=<folder with changed js>` points the replays at changed files instead of `site/v2/js`.
