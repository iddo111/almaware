# Alma Federation Worker source preview

This archive is for code review and private-lab testing. It is not a public
compute-sharing client yet.

Current safety boundary:

- arbitrary command strings and shell execution are rejected;
- only the structured system.info, python.version, and diagnostic.echo task
  kinds are accepted;
- the worker is dry-run by default and requires ALMA_EXECUTE=1 before the
  bounded executable task can run;
- a strong explicit enrollment token is mandatory;
- cleartext coordinator traffic is loopback-only; remote coordinators must use
  HTTPS;
- public onboarding, signed packaging, and Windows application-control
  verification are still required;
- never publish `.alma_token`, logs, machine state, or local configuration.

The public download page must keep the Windows installer disabled until those
checks pass on a clean machine.
