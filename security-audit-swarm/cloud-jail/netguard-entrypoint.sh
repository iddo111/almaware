#!/bin/sh
set -eu

# Cloud Shell exposes a Google metadata endpoint even when gcloud CLI
# authorization is disabled.  Networked audit phases run with CAP_NET_ADMIN
# only long enough to blackhole the metadata addresses, then permanently drop
# privileges and all capability bounding-set entries before executing any
# project-controlled code.
if [ "${AUDIT_OFFLINE:-0}" != "1" ]; then
  ip route replace blackhole 169.254.169.254/32
  ip route replace blackhole 169.254.169.253/32
fi

audit_uid="${AUDIT_UID:-65534}"
audit_gid="${AUDIT_GID:-65534}"

if [ -n "${AUDIT_CHOWN:-}" ]; then
  chown -R "${audit_uid}:${audit_gid}" "${AUDIT_CHOWN}"
fi

exec setpriv \
  --reuid="${audit_uid}" \
  --regid="${audit_gid}" \
  --clear-groups \
  --no-new-privs \
  --bounding-set=-all \
  "$@"
