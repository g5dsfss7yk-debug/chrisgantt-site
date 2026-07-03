# Pi-hole Setup Guide — CanaKit Raspberry Pi 4 (4GB) Starter PRO Kit

A step-by-step guide to turn your new Raspberry Pi 4 into a network-wide ad/tracker
blocker for your whole house. Once it's running, **every device on your Wi-Fi gets
ad-blocking automatically** — no per-device setup.

**Time required:** ~20–30 minutes
**Difficulty:** Beginner-friendly (copy/paste commands)

---

## 1. What's in the box (CanaKit 4GB PRO Kit)

Your kit includes everything you need:

- ✅ Raspberry Pi 4 Model B (4GB RAM)
- ✅ Case (3-piece, snap-together) + cooling fan + heatsinks
- ✅ CanaKit USB-C power supply (the good one — properly rated)
- ✅ microSD card, **pre-loaded with Raspberry Pi OS**
- ✅ USB microSD card reader
- ✅ 2× micro-HDMI cables

**You'll also want (not in the kit):**
- An **Ethernet cable** — strongly recommended so the Pi is wired to your router
  (a DNS server should not depend on Wi-Fi). Any Cat5e/Cat6 cable works.

---

## 2. Assemble the hardware

1. Attach the **heatsinks** to the chips on the board (peel the adhesive backing,
   press onto the two main chips).
2. Seat the Pi in the **case** and attach the **fan** — plug the fan's red wire to
   GPIO pin **4 (5V)** and black wire to pin **6 (GND)**. (CanaKit's included guide
   shows this; the fan is optional for a low-load Pi-hole but nice to have.)
3. Insert the **pre-loaded microSD card** into the slot on the underside of the Pi.
4. Plug in the **Ethernet cable** to the Pi and to a free port on your router.
5. **Don't plug in power yet** — do the setup prep in Step 3 first.

---

## 3. Prep the SD card for headless setup (recommended)

The card comes pre-loaded, but we want to enable **SSH** so you can control the Pi
from your laptop without a monitor/keyboard ("headless"). Easiest way is to re-flash
with **Raspberry Pi Imager**, which lets you bake in these settings:

1. On your computer, download and install
   [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Insert the microSD card using the included USB card reader.
3. In Imager:
   - **Device:** Raspberry Pi 4
   - **OS:** Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)** — no desktop
     needed, lighter and perfect for Pi-hole.
   - **Storage:** select the microSD card.
4. Click **Next → Edit Settings** and set:
   - **Hostname:** `pihole`
   - **Enable SSH** → "Use password authentication"
   - **Username / password:** pick your own (e.g. user `pi`) — write it down.
   - **Locale / timezone:** set yours.
   - (Skip Wi-Fi — we're using Ethernet.)
5. **Write** the card, then put it back in the Pi.

> Prefer using a monitor + keyboard instead? You can skip this whole step, boot with
> the pre-loaded OS, and just enable SSH later via `sudo raspi-config`. The headless
> route above is cleaner for a set-and-forget device.

---

## 4. First boot

1. Insert the card, make sure Ethernet is connected, then plug in **power**.
2. Wait ~60–90 seconds for it to boot.
3. From your computer's terminal, SSH in:
   ```bash
   ssh pi@pihole.local
   ```
   (Use whatever username you set. If `pihole.local` doesn't resolve, find the Pi's
   IP in your router's device list and use `ssh pi@<that-ip>` instead.)
4. Update the OS first:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   ```

---

## 5. Give the Pi a fixed IP address

Your network must always know where to find the Pi, so its IP can't change. The
Pi-hole installer (Step 6) sets a static IP on the Pi itself, which covers this. You
can *also* reserve it in your gateway for good measure.

> **AT&T gateway:** reservations live at `http://192.168.1.254` → Home Network →
> **IP Allocation**. (If you go with Option B in Step 7, Pi-hole runs DHCP anyway, so
> just make sure the Pi's own static IP falls **outside** the range Pi-hole hands out.)

1. Log into your router's admin page.
2. Find **DHCP reservations** (sometimes "Address Reservation" / "Static Leases").
3. Reserve the Pi's current IP to its MAC address. Find them on the Pi with:
   ```bash
   hostname -I        # shows current IP
   ip link            # shows MAC (the eth0 "link/ether" value)
   ```
4. Note the reserved IP — you'll point your router's DNS at it in Step 7.

---

## 6. Install Pi-hole

The one-line installer:

```bash
curl -sSL https://install.pi-hole.net | bash
```

> ⚠️ **If the installer quits at the "static IP" screen** (it prints
> `Installer exited at static IP message.`): the `curl | bash` method can lose its
> interactive input at that dialog. Use Pi-hole's officially-supported alternative —
> download and run it directly instead:
> ```bash
> sudo apt install -y git
> git clone --depth 1 https://github.com/pi-hole/pi-hole.git Pi-hole
> cd "Pi-hole/automated install/"
> sudo bash basic-install.sh
> ```
> This gives the wizard a real terminal and it sails through. *(Confirmed fix on a
> real Raspberry Pi 4 / Raspberry Pi OS Lite install.)*

The installer walks you through a few screens:

- **Upstream DNS provider:** Cloudflare (`1.1.1.1`) or Quad9 (`9.9.9.9`) are both great.
- **Blocklists:** accept the default list to start.
- **Static IP:** confirm the IP from Step 5.
- **Web admin interface + logging:** say **yes**.

At the end it prints your **admin web address** and a **password**. Write the password
down (or reset it later with `pihole setpassword`).

Visit the dashboard at:
```
http://pihole.local/admin
```
(or `http://<pi-ip>/admin`)

---

## 7. Point your network at Pi-hole ⭐ (the step that makes it network-wide)

> 🛑 **AT&T Fiber users read this.** AT&T gateways (BGW210 / BGW320 / BGW620
> "All-Fi Hub") **do not let you change the DNS server** they hand out to devices —
> that field is locked in AT&T's firmware. So the usual "set the router's DNS to the
> Pi" trick **does not work** on AT&T. Use one of the three AT&T-specific methods
> below instead.

### Option A — Per-device DNS (easiest, zero risk — great for a first test)

Leave the gateway untouched and point individual devices at Pi-hole manually.

- On each device's Wi-Fi/network settings, set **DNS** to your Pi-hole's IP (Step 5).
  - **Windows:** Network adapter → Properties → IPv4 → Preferred DNS = Pi IP
  - **macOS:** System Settings → Network → Details → DNS → add Pi IP
  - **iPhone/Android:** Wi-Fi → your network → configure DNS → Manual → Pi IP
- ✅ Simple, nothing to break, easy to undo. Perfect for confirming Pi-hole works.
- ❌ You repeat it per device; guests and IoT gadgets aren't covered.

### Option B — Let Pi-hole run DHCP (whole-house, no extra hardware)

Turn **off** the AT&T gateway's DHCP server and let Pi-hole hand out addresses + DNS.

> 🛑 **BGW320-505-specific warning — read first.** Fully disabling DHCP on the
> BGW320-505 has a track record of problems: the gateway can misbehave, and people
> have **locked themselves out** of the admin page (once DHCP is off, your PC no longer
> gets an IP to reach `192.168.1.254`). Do it carefully or skip to Option C.
>
> **Two rules that prevent the lockout:**
> 1. **Before** disabling the gateway's DHCP, set a **static IP on your admin
>    computer** (e.g. `192.168.1.10`, subnet `255.255.255.0`, gateway `192.168.1.254`)
>    so you can always reach the admin page.
> 2. **Don't** also disable the Wi-Fi radios in the same session — that combination is
>    what bricked people's access. Change one setting at a time.

**Steps:**

1. **In Pi-hole admin** (`http://pihole.local/admin`): Settings → **DHCP** →
   enable "**DHCP server enabled**". Set a range (e.g. `192.168.1.150`–`192.168.1.250`)
   and gateway `192.168.1.254` as the router. Save.
2. Set a **static IP on your admin computer** (see rule 1 above).
3. **On the gateway** (`http://192.168.1.254`, Device Access Code from the sticker):
   Home Network → **Subnets & DHCP** tab → **DHCP Server Enable → Off**. Save.
4. Reconnect a device (toggle Wi-Fi off/on) — it should now get its address and DNS
   from Pi-hole. Verify in the dashboard that queries appear.

> ⚠️ **IPv6 caveat (AT&T-specific):** even with the above, the gateway still advertises
> *itself* for **IPv6 DNS**, letting some devices bypass Pi-hole. The common fix is to
> **disable IPv6** on the gateway (Home Network → IPv6 → off) so all DNS is forced
> through Pi-hole over IPv4. If you'd rather keep IPv6, expect some ad-blocking "leakage."

### Option C — IP Passthrough + your own router (most bulletproof, costs money)

Put the AT&T gateway in **IP Passthrough** mode and run your own router behind it,
then set that router's DNS to the Pi (a normal router *does* allow this).

- ✅ Cleanest, most reliable, full control over your LAN.
- ❌ Requires buying a router (~$50–150) and extra setup. Only worth it if you want
  your own router anyway.

**Suggested path (BGW320-505):** start with **Option A** to confirm everything works
safely. For permanent whole-house coverage, **Option B** works with no new hardware
but carries the BGW320-505 lockout risk above — do it carefully. If you want the
*safest* rock-solid setup and don't mind buying a router, **Option C** is the best
long-term answer on AT&T fiber.

> ⚠️ **Reliability note:** Once Pi-hole is your DHCP/DNS (Option B), it becomes critical
> infrastructure — if the Pi is off, devices can't get online. Keep the AT&T gateway's
> DHCP toggle handy so you can flip it back on in a pinch, or add a **second Pi-hole**
> later as a backup DNS. Not needed to get started.

---

## 8. Test it

1. On a device connected to your network, visit the dashboard `http://pihole.local/admin`
   — you should see queries flowing in.
2. Confirm your device is actually using Pi-hole for DNS:
   ```bash
   nslookup pi.hole
   ```
   It should resolve to your Pi's IP.
3. Browse a few ad-heavy sites — you should notice fewer ads, and the dashboard's
   "Queries Blocked" counter climbing.

---

## 9. Recommended blocklists (optional upgrade)

Pi-hole ships with a good default list (StevenBlack's unified hosts), so you're
already blocking ads out of the box. If you want to block **more** — trackers, telemetry,
malware domains — add one or two well-curated lists below. These two are the community
favorites because they're aggressive *but* carefully maintained to minimize breaking
legitimate sites:

| List | URL | Notes |
|---|---|---|
| **OISD Big** | `https://big.oisd.nl` | Great all-round list; very low false-positives. A safe first add. |
| **HaGeZi Multi PRO** | `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/domains/pro.txt` | Blocks ads + tracking + some malware. Popular, well-maintained. |

> 💡 **Start conservative.** Add **OISD Big** first, live with it a few days, then add
> HaGeZi if you want more. Adding many overlapping lists at once just makes it harder to
> tell which list broke a site if something stops working.

### How to add a blocklist (Pi-hole v6 dashboard)

1. Open the dashboard: `http://pihole.local/admin` (log in with your admin password).
2. In the left sidebar, click **Lists** (older versions: *Group Management → Adlists*).
3. Paste the list's URL into the **"Address"** field.
4. (Optional) Add a comment like `OISD Big` so you remember what it is.
5. Click **Add**.
6. ⭐ **Important — apply it:** a new list isn't active until you rebuild the block
   database ("gravity"). Click **Update Gravity** (Tools → Update Gravity), or from SSH:
   ```bash
   pihole -g
   ```
7. Done. Check the dashboard — your total "Domains on Lists" number should jump.

### If a website or app breaks

Occasionally a stricter list blocks something you need. Fix it without removing the list:

1. Dashboard → **Domains** → add the domain to the **Allow** list, **or** from SSH:
   ```bash
   pihole allow example.com
   ```
2. Not sure which domain broke? Dashboard → **Query Log**, look for **red (blocked)**
   entries right when the site failed, and allow the one it needs.

### Removing a list

Lists → find the row → toggle it off (or delete) → **Update Gravity** again.

---

## 10. Maintenance (occasional, optional)

- **Update Pi-hole:** `pihole -up`
- **Update the OS:** `sudo apt update && sudo apt full-upgrade -y`
- **Update blocklists (gravity):** `pihole -g`
- **Temporarily disable blocking:** from the dashboard, or `pihole disable 5m`
- **Whitelist a site** that breaks: dashboard → *Domains* → add to allowlist, or
  `pihole allow example.com`

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Lightning-bolt / undervoltage icon | Use the included CanaKit power supply (not a phone charger). |
| SSH "Permission denied" no matter the password | SSH doesn't prompt for a username — it uses the one before the `@`. Connect as the username you set in the Imager (e.g. `ssh chrisgantt@pihole.local`), **not** `pi`. |
| Can't `ssh pihole.local` | Use the Pi's IP from the router's device list instead. |
| Installer quits at the "static IP" screen | Use the `git clone` + `sudo bash basic-install.sh` method (see Step 6). |
| Dashboard shows **0 queries** after setting a device's DNS | The device is using another DNS server *ahead* of Pi-hole. On the client, remove all other DNS servers (e.g. `1.1.1.1`) so **only** the Pi's IP remains — clients query the first server and skip Pi-hole otherwise. |
| Browser URL keeps going to a web search | Type the address in the **address bar** (top of the window), not the page's search box. Use the Pi's IP, e.g. `192.168.1.112/admin`. |
| A website/app breaks | Whitelist the domain it needs (dashboard → allowlist). |
| Ads still showing | Confirm the device's DNS is the Pi (Step 8); some devices cache DNS — reconnect Wi-Fi. |
| Whole network loses internet (Option B) | Re-enable **DHCPv4** on the AT&T gateway (Home Network → Subnets & DHCP) to restore normal service, then troubleshoot the Pi. |
| Ads leaking on some devices | Likely IPv6 bypass — disable IPv6 on the AT&T gateway (see Step 7, Option B caveat). |
| iPhone Safari not filtered | Turn off **iCloud Private Relay** for Wi-Fi (Settings → your name → iCloud → Private Relay). Cellular isn't covered by Pi-hole regardless. |

---

## Handy links

- Pi-hole docs: https://docs.pi-hole.net/
- Raspberry Pi Imager: https://www.raspberrypi.com/software/
- Pi-hole community forum: https://discourse.pi-hole.net/

Enjoy your ad-free network! 🎉
