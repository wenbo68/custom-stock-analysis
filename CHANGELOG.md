# Changelog

Every version of the app, newest first. The version is a git tag
(`vX.Y.Z`), a GitHub release with this section as its notes, and a
Docker image tag (`ghcr.io/wenbo68/custom-stock-analysis:X.Y.Z`), all
cut from the same commit. The numbers follow semantic versioning:
the last number for fixes, the middle for new features, the first for
changes that break how the app is installed or used.

## 0.1.0 — 2026-10-21

The first tagged release. Everything in the README is in it:

- **Analysis runs** for US, A-share, Hong Kong, Japanese, Korean and Taiwanese stocks: six data reports (technicals, fundamentals, positioning, macro economy, company news, world news), an outlook with a score whose reasons cite checked report values, and a trade plan sized from capital and risk.
- **Two tiers.** Tier 1 is one preliminary analysis; tier 2 is a deep analysis with graded evidence, a check round and a vote, the whole tree open to inspection.
- **Live reports.** A running run's cards fill in as each step lands, and a stop button ends a run at its next step boundary, keeping the sections that finished.
- **A chat page** whose bot reads and acts on the run history through the app's own API, asks before every action and large read, keeps every tool call on the record, summarizes the conversation when its context nears the limit, and reports back when a run it started ends.
- **Three languages** (English, Simplified Chinese, Korean) for the page and for everything the model writes, with a code check that the model answered in the chosen one.
- **Any model provider** litellm supports, one key, one optional cheaper model for news screening.
- **Install** from source with `start-server.sh`, or with Docker from the prebuilt image.
