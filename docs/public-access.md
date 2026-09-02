# Public Access

The existing deployment path uses WireGuard:

```text
Internet -> 103.116.104.34:8383 -> WireGuard server -> VPN client 10.0.50.2:8383 -> DuyGPT
```

## DuyGPT Machine

Start WireGuard:

```bash
sudo wg-quick up ./leduy_wg0.conf
```

Check:

```bash
ip -br addr
wg show
ss -ltnp | grep 8383
```

Expected DuyGPT listener:

```text
0.0.0.0:8383
```

## WireGuard Server

Enable IPv4 forwarding:

```bash
sudo sysctl -w net.ipv4.ip_forward=1
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-forward.conf
sudo sysctl --system
```

Forward public TCP port `8383` to `10.0.50.2:8383`:

```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 8383 -j DNAT --to-destination 10.0.50.2:8383
sudo iptables -A FORWARD -p tcp -d 10.0.50.2 --dport 8383 -j ACCEPT
sudo iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo iptables -t nat -A POSTROUTING -d 10.0.50.2 -p tcp --dport 8383 -j MASQUERADE
```

Open firewall:

```bash
sudo ufw allow 8383/tcp
```

## Test

```text
http://103.116.104.34:8383
```

```bash
curl -I http://103.116.104.34:8383/
```

## Security Notes

- Keep `REQUIRE_LOGIN=1` before exposing DuyGPT.
- Keep `DISABLE_REGISTRATION=0` if many users should self-register; set it to `1` for invitation/admin-created accounts.
- Set `DEVICE_API_KEY` for speaker/device API calls.
- Leave `CORS_ORIGIN` empty unless another trusted website must call this API from the browser.
- Put Nginx/Caddy in front and terminate HTTPS for production.
- Do not share WireGuard private key files.
