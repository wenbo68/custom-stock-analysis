# -*- coding: utf-8 -*-
"""The chat bot (2026-09-21): a model that answers questions about, and
acts on, this app's runs through the app's own API — and nothing else.

Design (owner discussion 2026-09-19):

- **Tools, not SQL.** The model is handed a menu of named actions
  (``tools.py``) that call the same Python functions the HTTP routes
  call. It never sees the database, the source code, or the API key.
  Every tool is a route the web page also has ("never give the bot an
  ability the app itself doesn't have").
- **Two copies of every result.** The model gets a compact result it
  can reason over; the chat page shows the user the trace of what was
  called and what came back. Large reads (a data report, one AI call's
  text) and every state change (start a run, delete a run) wait for
  the user's yes — a priced, explicit choice, since the user pays for
  the tokens with their own key.
- **A small harness** (``harness.py``): the loop that sends the
  conversation to the model, runs the tools it asks for, feeds the
  results back, and stops — at the tool-call limit, on a plain answer, or to
  ask the user. Conversations live in the database (``store.py``), so
  the bot's memory is exactly what the page shows.
"""
