# tiny-paywall2

Micropayment article marketplace — see `SPEC.md` for the full design and `CLAUDE.md`
for how the code works today. (Full README lands in Phase E.)

## Admin bootstrap (one-time)

Register an account through the UI, then flag it as admin directly in Mongo:

```
mongosh "<your MONGO_URI>" --eval 'db.users.updateOne({email: "you@example.com"}, {$set: {is_admin: true}})'
```

Log out and back in is not required — the flag is read live on each request.

## Mongo replica set (one-time, required since Phase D)

Money moves in multi-document transactions, which MongoDB only allows on a replica
set — a **single-node** replica set is sufficient. The backend refuses to start
without transaction support (startup probe in `db/connection.py`).

Local Windows service **with authentication enabled** (keyfile is mandatory —
MongoDB requires internal auth when authorization + replication are both on):

1. Generate a keyfile (Git Bash):
   ```
   openssl rand -base64 756 > /c/ProgramData/MongoDB/mongo-keyfile
   ```
2. Edit `mongod.cfg` (usually `C:\Program Files\MongoDB\Server\<version>\bin\mongod.cfg`) — add
   `replication.replSetName` and `security.keyFile` (merge `keyFile` under the
   existing `security:` block if one exists):
   ```yaml
   replication:
     replSetName: rs0
   security:
     authorization: enabled
     keyFile: C:\ProgramData\MongoDB\mongo-keyfile
   ```
3. Restart the service from an **elevated** terminal:
   ```
   net stop MongoDB && net start MongoDB
   ```
4. Initiate the replica set once. The member `host` is the address the set
   *advertises* to every client during driver discovery — pick one all clients can
   reach. This machine binds `127.0.0.1,10.0.0.252` and other LAN machines connect
   to it, so we advertise the LAN IP (currently configured):
   ```
   mongosh mongodb://localhost:27017 --eval "rs.initiate({_id: 'rs0', members: [{_id: 0, host: '10.0.0.252:27017'}]})"
   ```
   Single-machine setups would use `localhost:27017` instead. To change it later:
   `cfg = rs.conf(); cfg.members[0].host = '<new>:27017'; rs.reconfig(cfg)`.
   If the LAN IP ever changes, update both `bindIp` in `mongod.cfg` and this
   advertised host.
5. Append `directConnection=true` to `MONGO_URI` in the root `.env`:
   `mongodb://...@localhost:27017/tiny?directConnection=true`

Reverting: remove the two config lines and restart the service.

## Stripe (test mode, required since Phase D)

1. Create a free Stripe account; grab the **test** secret key (`sk_test_…`) from
   Developers → API keys → put it in `.env` as `STRIPE_SECRET_KEY`.
2. Install the [Stripe CLI](https://stripe.com/docs/stripe-cli) and run `stripe login` once.
3. While developing payments, run the webhook forwarder (it prints the
   `whsec_…` secret — put it in `.env` as `STRIPE_WEBHOOK_SECRET`):
   ```
   stripe listen --forward-to localhost:1864/stripe/webhook
   ```
4. Test card: `4242 4242 4242 4242`, any future expiry, any CVC.
