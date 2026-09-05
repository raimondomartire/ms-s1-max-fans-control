#!/usr/bin/env bash
# Compila, firma (MOK akmod arruolata), INSTALLA in /lib/modules/.../extra con
# label SELinux corretta (modules_object_t) e carica il modulo strixec per il
# kernel CORRENTE. Idempotente. Usato da strixec.service all'avvio → sopravvive
# agli aggiornamenti di kernel.
#
# NB: il modulo DEVE stare in /lib/modules/<krel>/extra (tipo SELinux
# modules_object_t) per poter essere caricato dal contesto di servizio
# (unconfined_service_t). In /opt (usr_t) SELinux nega module_load.
set -euo pipefail

SRC=/opt/strixec
KREL="$(uname -r)"
KDIR="/lib/modules/$KREL/build"
DEST="/lib/modules/$KREL/extra"
KEY=/etc/pki/akmods/private/private_key.priv
CRT=/etc/pki/akmods/certs/public_key.der

log(){ printf '[strixec] %s\n' "$*"; }

if [[ -e /dev/strixec ]]; then
  log "/dev/strixec già presente, nulla da fare."
  exit 0
fi
if lsmod | grep -q '^strixec'; then
  modprobe -r strixec 2>/dev/null || rmmod strixec 2>/dev/null || true
fi
if [[ ! -d "$KDIR" ]]; then
  log "ERRORE: kernel-devel per $KREL assente ($KDIR)."
  exit 1
fi

log "Compilo per kernel $KREL…"
make -C "$SRC" clean >/dev/null 2>&1 || true
make -C "$SRC" >/dev/null

if [[ -f "$KEY" && -f "$CRT" ]]; then
  log "Firmo con la chiave MOK akmod…"
  "$KDIR/scripts/sign-file" sha256 "$KEY" "$CRT" "$SRC/strixec.ko"
else
  log "ATTENZIONE: chiave MOK akmod assente; il load fallirà sotto Secure Boot."
fi

log "Installo in $DEST con label SELinux corretta…"
mkdir -p "$DEST"
install -m 0644 "$SRC/strixec.ko" "$DEST/strixec.ko"
# label modules_object_t (necessaria per module_load da contesto di servizio)
restorecon -F "$DEST/strixec.ko" 2>/dev/null || \
  chcon -t modules_object_t "$DEST/strixec.ko" 2>/dev/null || true
depmod -a "$KREL"

log "Carico il modulo (modprobe)…"
modprobe strixec

if [[ -e /dev/strixec ]]; then
  log "OK: /dev/strixec pronto."
else
  log "ERRORE: modulo caricato ma /dev/strixec assente."
  exit 1
fi
