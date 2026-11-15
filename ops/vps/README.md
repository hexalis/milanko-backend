# VPS operations

Order of operations for a fresh host:

1. `sudo ops/vps/bootstrap.sh` — packages, swap, `deploy` user, directories,
   Docker network and UFW.
2. Create the PostgreSQL container, roles and databases (see
   [`../../docs/data-seed.md`](../../docs/data-seed.md)).
3. Restore the dump into `milanko_develop` and clone QA/production.
4. Write `/etc/milanko/backend-<env>.env` and
   `/etc/milanko/api-keys-<env>.tsv`.
5. `sudo ops/vps/apply-nginx.sh` — installs the nginx site, API-key maps,
   Cloudflare real-IP ranges and reloads nginx.
6. Obtain the Let's Encrypt certificate (see
   [`../../docs/infrastructure.md`](../../docs/infrastructure.md)).
7. Configure the GitHub Environments and push `develop`.
8. Install the ingestion timers once the ingestion modules exist:
   `sudo ops/systemd/install-all.sh`.

Do not commit real API keys, database passwords or `.env` files. The nginx
snippets and TSV files live only on the VPS.
