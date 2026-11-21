#!/usr/bin/env bash
# Wolthusen Hub: frischen VPS absichern (Debian 12 / Ubuntu 22.04 / 24.04), einmalig VOR setup.sh
# Aufruf:  sudo bash server-haerten.sh
#
# Was passiert (jeder Schritt mit Rückfrage, wo er dich aussperren könnte):
#   1. System aktualisieren, automatische Sicherheitsupdates einschalten
#   2. Zeitzone Europe/Berlin, Auslagerungsdatei bei wenig Arbeitsspeicher
#   3. Firewall (ufw): nur SSH, 80 und 443 offen
#   4. fail2ban: sperrt IPs nach wiederholten falschen SSH-Anmeldungen
#   5. Optional: eigener Benutzer mit sudo, danach SSH nur noch mit Schlüssel und ohne root-Anmeldung
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo ausführen: sudo bash server-haerten.sh"; exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Dieses Skript ist für Debian oder Ubuntu."; exit 1
fi
ask() { local a; read -rp "$1 [j/N] " a; [[ "$a" =~ ^[jJyY]$ ]]; }

echo "== 1. System aktualisieren und automatische Sicherheitsupdates =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq unattended-upgrades ufw fail2ban curl git ca-certificates
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CFG'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CFG
echo "-> Sicherheitsupdates werden jetzt täglich automatisch eingespielt."

echo "== 2. Zeitzone und Arbeitsspeicher =="
timedatectl set-timezone Europe/Berlin 2>/dev/null || true
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 2000 ] && [ -z "$(swapon --show --noheadings)" ]; then
  echo "-> Nur ${MEM_MB} MB Arbeitsspeicher und keine Auslagerung: lege 1 GB /swapfile an (hilft beim Bauen des Containers)."
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== 3. Firewall =="
SSH_PORT=$(sshd -T 2>/dev/null | awk '/^port / {print $2; exit}')
SSH_PORT=${SSH_PORT:-22}
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "${SSH_PORT}/tcp" comment 'SSH' >/dev/null
ufw allow 80/tcp comment 'HTTP (Zertifikat und Umleitung)' >/dev/null
ufw allow 443/tcp comment 'HTTPS' >/dev/null
ufw allow 443/udp comment 'HTTP/3' >/dev/null
ufw --force enable >/dev/null
echo "-> Offen: SSH (${SSH_PORT}), 80, 443. Alles andere ist zu."
echo "   Hinweis: Hat der Anbieter eine eigene Firewall im Kundenmenü, dort dieselben Ports freigeben."

echo "== 4. fail2ban =="
cat > /etc/fail2ban/jail.d/wolthusen.local <<CFG
[sshd]
enabled  = true
port     = ${SSH_PORT}
backend  = systemd
maxretry = 5
findtime = 10m
bantime  = 1h
CFG
systemctl enable --now fail2ban >/dev/null 2>&1
systemctl restart fail2ban
echo "-> IPs mit 5 falschen SSH-Anmeldungen in 10 Minuten werden 1 Stunde gesperrt."

echo "== 5. Benutzer und SSH =="
echo "Empfehlung: nicht dauerhaft als root arbeiten, sondern mit einem eigenen Benutzer (z. B. wolthusenhub) und SSH-Schlüssel."
if ask "Eigenen Benutzer mit sudo anlegen bzw. vorhandenen nutzen?"; then
  read -rp "Benutzername [wolthusenhub]: " NEWUSER; NEWUSER=${NEWUSER:-wolthusenhub}
  if ! [[ "$NEWUSER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then echo "Ungültiger Name."; exit 1; fi
  if ! id "$NEWUSER" >/dev/null 2>&1; then
    adduser --gecos "" "$NEWUSER"
  fi
  usermod -aG sudo "$NEWUSER"
  HOME_DIR=$(getent passwd "$NEWUSER" | cut -d: -f6)
  install -d -m 700 -o "$NEWUSER" -g "$NEWUSER" "$HOME_DIR/.ssh"
  if [ -s /root/.ssh/authorized_keys ] && [ ! -s "$HOME_DIR/.ssh/authorized_keys" ]; then
    cp /root/.ssh/authorized_keys "$HOME_DIR/.ssh/authorized_keys"
    echo "-> SSH-Schlüssel von root für $NEWUSER übernommen."
  fi
  if [ ! -s "$HOME_DIR/.ssh/authorized_keys" ]; then
    echo "Für $NEWUSER ist noch kein SSH-Schlüssel hinterlegt. Öffentlichen Schlüssel einfügen (eine Zeile, beginnt mit ssh-ed25519),"
    read -rp "oder leer lassen zum Überspringen: " KEY
    if [[ "$KEY" =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-[a-z0-9-]+)\ [A-Za-z0-9+/=]+ ]]; then
      echo "$KEY" >> "$HOME_DIR/.ssh/authorized_keys"
    fi
  fi
  [ -f "$HOME_DIR/.ssh/authorized_keys" ] && chown "$NEWUSER:$NEWUSER" "$HOME_DIR/.ssh/authorized_keys" && chmod 600 "$HOME_DIR/.ssh/authorized_keys"
  if command -v docker >/dev/null 2>&1 || getent group docker >/dev/null; then usermod -aG docker "$NEWUSER" 2>/dev/null || true; fi

  if [ -s "$HOME_DIR/.ssh/authorized_keys" ]; then
    echo
    echo "WICHTIG: Bevor du weitermachst, in einem ZWEITEN Fenster testen:  ssh $NEWUSER@<Server-IP>  und dort  sudo -v"
    echo "Erst wenn das klappt, Passwort- und root-Anmeldung abschalten. Sonst sperrst du dich aus."
    if ask "Anmeldung als $NEWUSER mit Schlüssel und sudo erfolgreich getestet? Jetzt SSH nur noch mit Schlüssel und ohne root erlauben?"; then
      mkdir -p /etc/ssh/sshd_config.d
      cat > /etc/ssh/sshd_config.d/10-wolthusen.conf <<'CFG'
# Wolthusen Hub (server-haerten.sh): nur Schlüssel, kein root
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
CFG
      if sshd -t; then
        systemctl reload ssh 2>/dev/null || systemctl reload sshd
        echo "-> SSH: nur noch mit Schlüssel, root-Anmeldung aus. Ab jetzt:  ssh $NEWUSER@<Server-IP>"
      else
        rm -f /etc/ssh/sshd_config.d/10-wolthusen.conf
        echo "SSH-Konfiguration fehlerhaft, Änderung zurückgenommen."
      fi
    else
      echo "-> SSH bleibt unverändert. Später erneut ausführen, wenn der Test geklappt hat."
    fi
  else
    echo "-> Kein Schlüssel hinterlegt, SSH bleibt unverändert."
  fi
fi

echo
echo "Fertig. Nächste Schritte stehen in UMZUG-VPS.md (Repository holen, setup.sh, Daten umziehen)."
echo "Firewall:  ufw status    |    Gesperrte IPs:  fail2ban-client status sshd"
