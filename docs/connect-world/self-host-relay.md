# Run your own Connect World relay

Connect World lets your iPhone reach the OLIVE computer at home when you are somewhere else. Both
devices connect **out** to a small server you rent, called a *relay*. You need no VPN and no router
port forwarding.

This guide assumes you have never run a server before. It takes about an hour, and the server
costs a few euros a month. Every example uses the placeholder name **`world-relay.example.com`**:
replace it with your own name everywhere.

> **Before you start.** The relay files (the `world-relay/` folder plus the `olive/world` and
> `olive/world_relay` sources it builds from) are not yet published as a separate download. Ask
> whoever gave you OLIVE for the relay bundle, and unpack it on the server in step 7.

## What the relay can and cannot see

| The relay operator **can** see | The relay operator **cannot** see |
| --- | --- |
| The IP addresses of your devices | Your prompts and OLIVE's answers |
| When devices connect, and for how long | Notes, drawings, files, file names or media |
| How many bytes move, and when | Device names or identities |
| That a route exists (an opaque key) | Any key that could decrypt your session |

Your devices encrypt everything end to end with their own pinned TLS 1.3 session. The relay only
passes those bytes along. It stores nothing, runs no AI and keeps no database.

## 1. Get a domain name

A domain is a name such as `example.com`. You need one so your relay can have an HTTPS certificate.

- A **registrar** sells you the domain (for example Namecheap, Gandi or Porkbun). You pay yearly.
- A **DNS provider** answers the question "which IP address is `world-relay.example.com`?". Most
  registrars include DNS. You can also use a separate DNS provider (for example Cloudflare DNS or
  deSEC); then you change the domain's *nameservers* at the registrar to point at that provider.

You only need one name for the relay, usually a subdomain such as `world-relay.example.com`.

## 2. Rent a small Linux server (VPS)

Rent a **virtual private server** from any hosting company (for example Hetzner, OVH, DigitalOcean
or Vultr):

- the smallest plan is enough: 1 vCPU, 512 MB to 1 GB RAM, 10 GB disk;
- choose **Ubuntu 24.04 LTS** as the operating system (this guide's commands are for it);
- choose a location near where you usually travel;
- make sure it has a public IPv4 address (IPv6 as well is fine).

**Bandwidth.** Every byte you send through World crosses the relay twice (in, then out). Watching
a 100 MB video through World uses about 200 MB of relay traffic. At home, OLIVE uses your local
network instead, so home use costs nothing.

## 3. Create an SSH key

SSH is how you log in to the server. A key is safer than a password.

On your own computer (Linux, macOS, or Windows PowerShell):

```sh
ssh-keygen -t ed25519 -C "my-relay"
```

Press Enter to accept the file name, and choose a passphrase. This creates a private key
(`~/.ssh/id_ed25519`, never share it) and a public key (`~/.ssh/id_ed25519.pub`).

When you create the VPS, paste the **public** key (the `.pub` file's contents) into the hosting
company's "SSH keys" field. Then log in:

```sh
ssh root@YOUR_SERVER_IP
```

## 4. Prepare the server

Update it and create an ordinary user for yourself:

```sh
apt update && apt upgrade -y
adduser relay
usermod -aG sudo relay
mkdir -p /home/relay/.ssh
cp ~/.ssh/authorized_keys /home/relay/.ssh/
chown -R relay:relay /home/relay/.ssh
chmod 700 /home/relay/.ssh && chmod 600 /home/relay/.ssh/authorized_keys
```

Open a **second** terminal and check that `ssh relay@YOUR_SERVER_IP` works before you continue.
From now on, use that user.

## 5. Point your name at the server (DNS)

At your DNS provider, add records for `world-relay` (the full name becomes
`world-relay.example.com`):

| Type | Name | Value |
| --- | --- | --- |
| A | `world-relay` | your server's IPv4 address |
| AAAA | `world-relay` | your server's IPv6 address (only if it has one) |

If your DNS provider offers a "proxy" or "CDN" switch (an orange cloud, for example), turn it
**off** for this record: the relay needs a direct connection.

Check it from your computer after a few minutes:

```sh
nslookup world-relay.example.com
```

It should print your server's address.

## 6. Install Docker and open the firewall

Install Docker with the Compose plugin (Ubuntu 24.04):

```sh
sudo apt install -y docker.io docker-compose-v2 ufw
sudo usermod -aG docker relay
```

On another Linux distribution, install Docker Engine and the Compose plugin with Docker's own
instructions (docs.docker.com/engine/install) instead.

Log out and back in so the group change applies, then check `docker compose version`.

Allow only SSH (22), HTTP (80) and HTTPS (443):

```sh
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Port 80 is used only to obtain the HTTPS certificate. If your hosting company has its own
firewall panel, allow the same three ports there too.

## 7. Configure and start the relay

Copy the relay bundle to the server and unpack it (for example to `~/olive-relay`), then:

```sh
cd ~/olive-relay/world-relay
cp relay.env.example relay.env
nano relay.env
```

Change only this line, to your own name:

```
OLIVE_WORLD_DOMAIN=world-relay.example.com
```

Save (Ctrl+O, Enter) and exit (Ctrl+X). `relay.env` holds no secrets: the relay has none.

Start it:

```sh
docker compose --env-file relay.env up -d --build
```

This starts two containers:

- **Caddy** answers on ports 80 and 443 and gets a free TLS certificate from Let's Encrypt
  automatically (and renews it);
- **the relay** runs behind Caddy on a private network, as an unprivileged user with a read-only
  filesystem.

## 8. Check health and readiness

```sh
./healthcheck.sh https://world-relay.example.com
```

You should see something like:

```
{"active_tunnels": 0, "protocol": "olive-world/1", "status": "ok", "version": "..."}
readiness 200
```

If the first request fails, wait a minute (the certificate is being issued) and try again. See
*Troubleshooting* below.

## 9. Connect OLIVE to your relay

Your relay's address is:

```
wss://world-relay.example.com
```

On the OLIVE computer: **Devices › This computer › OLIVE Connect World › Advanced › Relay URL**.
Enter the address, select **Use relay**, then turn Connect World **On**. (The setup wizard's
"Use OLIVE away from home?" step shows the same panel.)

## 10. Provision your iPhone at home (Direct)

Your iPhone receives its World route only over an authenticated local connection:

1. pair the iPhone with OLIVE if you have not yet (Devices › Pair iPhone);
2. open OLIVE on the iPhone while it is on the **same Wi-Fi** as the computer;
3. wait until it shows it is set up for Connect World.

## 11. Test from the mobile network

1. On the iPhone, turn **Wi-Fi off** so it uses cellular data.
2. Open OLIVE. It should show **Connected · World**.
3. Send a short message with FAST. The answer comes from your computer at home.
4. Turn Wi-Fi back on at home: the phone returns to the direct local connection by itself.

## 12. Harden SSH (key-only login)

Once key login works for your `relay` user, turn off password login:

```sh
sudo nano /etc/ssh/sshd_config.d/99-hardening.conf
```

Add:

```
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
```

Then `sudo systemctl reload ssh`. **Keep your current session open** and test a new
`ssh relay@YOUR_SERVER_IP` in another terminal before closing it.

## 13. Reboot test

```sh
sudo reboot
```

After a minute, run the health check from step 8 again. The containers restart on their own
(`restart: unless-stopped`), and your iPhone reconnects by itself.

## 14. Updating

When you receive a new relay bundle, replace the files and run:

```sh
cd ~/olive-relay/world-relay
docker compose --env-file relay.env up -d --build
```

Devices reconnect within seconds. Also keep the server itself updated:

```sh
sudo apt update && sudo apt upgrade -y
```

There is nothing to back up: the relay keeps no data. (Caddy's certificate is re-issued
automatically if it is lost.)

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `nslookup` shows no address or the wrong one | The A/AAAA record name and value; DNS changes can take up to an hour; the record must not be proxied |
| Health check: "connection refused" or a timeout | `docker compose ps` shows both containers *running*; the firewall allows 80 and 443 (both `ufw` and the hosting panel) |
| Health check: certificate error | Caddy could not get a certificate: DNS must point at this server and port 80 must be open. See `docker compose logs caddy` |
| OLIVE says the relay URL is invalid | It must start with `wss://` and contain no spaces |
| OLIVE says the relay is unreachable | Run the health check from another network; check that the server is up |
| The iPhone never shows "Connected · World" | Provision it on home Wi-Fi first (step 10); Connect World must be **On** on the computer, and the computer must be awake and running OLIVE |
| The iPhone shows World at home | It switches back to Direct once it sees the computer on the local network; give it a few seconds |
| `readiness 503` | The relay is shutting down or restarting; wait and retry |

Logs: `docker compose logs relay` shows only anonymous connection events. They never include
addresses, device identities, route credentials or content.

## Where to learn more

- `world-relay/README.md`: ports, limits, nginx or systemd instead of Docker, resource use.
- `docs/connect-world/protocol.md`: the protocol and security design.
