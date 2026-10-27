# Security

Cantrip runs on your own computer and uses your own keys (AI, search, GitHub and CRM tokens). We take problems that could leak those keys, or the leads you collect, seriously.

## Reporting a problem

Please don't open a public issue for a security problem. Report it privately instead:

1. Go to the repository's **Security** tab and press **Report a vulnerability**.
2. Say what you found, how to reproduce it, and which version or commit you used.

We'll reply within a week, keep you posted while we fix it, and credit you in the release notes if you'd like.

## Supported versions

Only the latest release on `main` gets security fixes while Cantrip is at 0.x.

## Keeping your keys safe

- Keep keys in environment variables, never in files you commit. `.env` and `cantrip.toml` are already in `.gitignore`.
- The app (`cantrip ui`) listens only on 127.0.0.1. Don't expose it to a network.
- Give CRM tokens the smallest scopes that work (for HubSpot: contacts read and write).
- Cantrip never sends messages on its own. If you find a path that does, that's a security problem: please report it.
