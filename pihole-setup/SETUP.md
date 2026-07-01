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

Your router must always know where to find the Pi, so its IP can't change. Easiest
method: **DHCP reservation** in your router.

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

One command does it all:

```bash
curl -sSL https://install.pi-hole.net | bash
```

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

This is what turns on ad-blocking for **every device**. Best method is at the router
so you don't have to touch each device:

1. Log into your router.
2. Find the **DNS server** setting (usually under **DHCP / LAN settings**, *not* the
   internet/WAN section).
3. Set the **Primary DNS** to your Pi-hole's IP (from Step 5).
4. **Secondary DNS:** see the reliability note below.
5. Save. Reboot the router (or just reconnect a device) so clients pick up the new DNS.

> ⚠️ **Reliability note:** Whatever you set as DNS becomes critical infrastructure — if
> it's down, the house "loses internet." Two safe choices:
> - Leave the secondary DNS **blank** so all queries go through Pi-hole (best blocking),
>   accepting that if the Pi is off, you'll need to change it back, **or**
> - Set a secondary like `1.1.1.1`. Note: devices may sometimes use the secondary and
>   bypass blocking, so it trades a little ad-blocking for resilience.
>
> The bulletproof option is running a **second Pi-hole** as the secondary DNS, but
> that's a later upgrade — not needed to get started.

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

## 9. Maintenance (occasional, optional)

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
| Can't `ssh pihole.local` | Use the Pi's IP from the router's device list instead. |
| A website/app breaks | Whitelist the domain it needs (dashboard → allowlist). |
| Ads still showing | Confirm the device's DNS is the Pi (Step 8); some devices cache DNS — reconnect Wi-Fi. |
| Whole network loses internet | Temporarily set router DNS back to `1.1.1.1`, then troubleshoot the Pi. |

---

## Handy links

- Pi-hole docs: https://docs.pi-hole.net/
- Raspberry Pi Imager: https://www.raspberrypi.com/software/
- Pi-hole community forum: https://discourse.pi-hole.net/

Enjoy your ad-free network! 🎉
