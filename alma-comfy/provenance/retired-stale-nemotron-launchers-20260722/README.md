# Retired stale Nemotron launchers

Removed on 2026-07-22 after fresh inspection because none represented the
accepted one-model, two-machine PP2 runtime:

- DGX1 `/home/eran1/alma-harness/nemotron_deploy.sh` (4,014 bytes) launched an
  independent single-node replica.
- DGX2 `/home/eran2/alma-harness/nemotron_deploy.sh` (4,014 bytes) launched an
  independent single-node replica.
- DGX1 `/usr/local/sbin/nemotron-cluster-start` (1,537 bytes) launched obsolete
  PP=3 settings on the wrong interface.
- DGX1 `/etc/systemd/system/nemotron-cluster-watchdog.service` (196 bytes) was
  static/inactive and targeted obsolete container `nemotron-cluster`.

The live `nemotron2-ray-head`, `nemotron2-ray-worker`, and `nemotron2-api`
containers were not altered. Their exact accepted configuration is recorded in
the canonical PP2 runtime manifest and verification script.
