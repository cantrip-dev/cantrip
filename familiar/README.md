# Cantrip Familiar

A [Guild](https://www.guild.ai/) agent that scouts leads with your deployed Cantrip, around the clock, and
never sends a thing.

Every morning it casts a spell on your copy of Cantrip (say, on your repo's contributors), takes the five
best leads, reads each one's public GitHub to find one true detail to open with, and hands you a digest
of drafts to review. The nightmare GTM bot spams everyone; this one can't:

- **No tool can send.** The Familiar gets two tools: cast a spell, and read public GitHub profiles.
  Nothing that posts, emails or comments.
- **Guild enforces it, not the prompt.** A credential rule lets the Familiar make only `GET` requests
  with your GitHub connection, so even a confused model can't write anything.
- **No keys in the agent.** Guild holds your Cantrip password and your GitHub connection and adds
  them to each request itself; the agent never sees them.
- **Your profile, your pitch.** Cantrip scores and drafts from your own profile. The Familiar only
  rewrites the first line of a draft around a detail it found, and keeps your pitch and ask word for word.

```
Guild schedule (9 AM) -> Cantrip Familiar -> cantrip_cast -> your Cantrip on Render -> scored leads + drafts
                                          -> GitHub (read-only) -> one true opening detail per lead
                                          -> digest in the Guild session, for a human to review
```

## Set it up

You need Cantrip deployed with a password (the [Render button](../README.md#deploy-it) is the quickest;
add a read-only `GITHUB_TOKEN` there for more GitHub lookups), a Guild account, and the
[Guild CLI](https://docs.guild.ai/quickstart) (`npm install -g @guildai/cli && guild auth login`).
Below, `ACCOUNT` is your Guild account name and `URL` is your Cantrip's address.

**1. Connect Cantrip to Guild** as a custom integration. Guild sends your password as HTTP Basic auth:

```sh
guild integration create cantrip --base-url URL --auth-scheme api-key \
  --header-template "Authorization: Basic {token}" --description "Cast Cantrip spells"
guild integration operation create ACCOUNT~cantrip --operation cantrip_cast --method POST --path /api/run \
  --summary "Cast a spell and return scored leads with drafted first notes" \
  --input-body-schema familiar/cast-input.json --output-body-schema familiar/cast-output.json
# The token is base64 of ":" plus your CANTRIP_PASSWORD. The CLI asks for it, so it stays out of your shell history.
python3 -c "import base64, getpass; print(base64.b64encode((':' + getpass.getpass('Cantrip password: ')).encode()).decode())"
guild integration connect ACCOUNT~cantrip --owner ACCOUNT
guild integration version build ACCOUNT~cantrip --version-number 1.0.0
guild integration version publish ACCOUNT~cantrip --version-number 1.0.0
```

**2. Create the agent** from this folder's `agent/` files (replace `YOUR_ACCOUNT` in `guild.yaml` first):

```sh
guild agent init --name cantrip-familiar --agent-type GUILD_NATIVE --category sales-marketing
cp familiar/agent/PROMPT.md familiar/agent/guild.yaml cantrip-familiar/
cd cantrip-familiar && guild agent save --message "Cantrip Familiar" --publish && cd ..
```

Connect GitHub under **Access & setup > Credentials** in Guild if you haven't yet.

**3. Keep GitHub read-only for the Familiar.** Find your GitHub credential's id with
`guild api GET /accounts/ACCOUNT/credentials`, then:

```sh
guild credentials policy create GITHUB_CREDENTIAL_ID --decision DENY --operations "*" \
  --agents ACCOUNT~cantrip-familiar --resources '{"methods":["POST","PUT","PATCH","DELETE"]}'
```

**4. Wake it every morning** in a workspace of its own:

```sh
guild workspace create cantrip-familiar
guild workspace agent add ACCOUNT~cantrip-familiar --workspace ACCOUNT~cantrip-familiar
guild trigger create --workspace ACCOUNT~cantrip-familiar --type time --agent ACCOUNT~cantrip-familiar \
  --name "Morning scout" --frequency CRON --cron-expression "0 9 * * *" --cron-timezone America/Los_Angeles \
  --input '{"text":"Scout the contributors to OWNER/REPO and give me the digest."}'
```

One trigger can name several repos ("Scout the contributors to a/b, c/d and e/f"); the digest gets a section for each.
Each morning's digest is a session in that workspace. To try it now, open the workspace's **Chat**,
`@`-mention the Familiar, and ask it to scout a repo or paste a guest list.

## Good to know

- A free Render instance sleeps when idle; the first cast of the day waits up to a minute while it wakes.
- The Familiar asks Cantrip for at most 30 people and keeps the best 5, so a run costs a handful of model
  calls and GitHub lookups.
- It follows the same workflow as the spells' `SPELL.md` files: score, shortlist, read their public work,
  rewrite each note around one true detail, hand the drafts to a human.
