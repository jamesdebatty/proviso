# reports-client

Copy `.env.example` to `.env`, fill in the token issued by the reports team,
then confirm the client is configured:

    python3 tools/reports_check.py

`REPORTS_API_TOKEN` set in the environment wins over `.env`. Neither file in
this repository holds a token: `.env.example` ships the literal placeholder
`REPLACE_ME`, and the check never echoes a token value, only its length.
