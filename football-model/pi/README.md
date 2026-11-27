# Raspberry Pi app (Pi 4, 4 GB)

One card for every NFL game (v11 game model + teasers, price gap, weather Unders + every pre-bet check), a form to
price any DK prop (v8 + checks, saved to the DK price log), and the live scoreboard. Open it on your phone on home Wi-Fi.
Measured in the cloud: a card run peaks at ~1.1 GB RAM; data ~170 MB. Speed on the Pi is not measured yet.

## Set up (once)
1. On the Pi: `git clone https://github.com/g5dsfss7yk-debug/chrisgantt-site.git && cd chrisgantt-site && git checkout claude/modest-galileo-zg0mve`
   (private repo: sign in with a GitHub token when git asks).
2. `bash football-model/pi/setup.sh`  - installs Python packages and downloads all data (play-by-play is the big one).
3. Keys (never commit them): `sudo nano /etc/environment` and add
   `CFBD_API_KEY=...` (collegefootballdata.com) and `DDS_API_KEY=...` (the-odds-api.com). Log out and back in.
4. Clock: `sudo timedatectl set-timezone America/Chicago`
5. App always on: `sudo cp football-model/pi/betting-app.service /etc/systemd/system/ && sudo systemctl enable --now betting-app`
   (edit User / paths in the file if your user is not `pi`).
6. Schedule: `crontab football-model/pi/crontab.txt`
7. Find the Pi's address: `hostname -I` -> open `http://<that address>:8080` on your phone.

## Use
- **Card**: press Refresh ~90 min before kickoff (inactives). Bet TESTED PICKs only; skip NOT VERIFIED; max 3 bets a game.
- **Prop**: type the player, stat, line (2+ catches = 1.5, anytime TD = 0.5) and DK's Over/Under price from the slip.
- **Scoreboard**: live record + DK price-log progress + the learning layer.

## Update the code later
`cd ~/chrisgantt-site && git pull`  (the pick log and price log are files on the Pi; if git says they conflict, keep the Pi's copy).
