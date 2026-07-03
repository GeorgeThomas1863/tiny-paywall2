# tiny-paywall2

Micropayment article marketplace — see `SPEC.md` for the full design and `CLAUDE.md`
for how the code works today. (Full README lands in Phase E.)

## Admin bootstrap (one-time)

Register an account through the UI, then flag it as admin directly in Mongo:

```
mongosh "<your MONGO_URI>" --eval 'db.users.updateOne({email: "you@example.com"}, {$set: {is_admin: true}})'
```

Log out and back in is not required — the flag is read live on each request.
