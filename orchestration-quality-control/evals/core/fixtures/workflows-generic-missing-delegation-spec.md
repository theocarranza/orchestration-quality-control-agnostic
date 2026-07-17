---
description: Summarize a customer support ticket and draft a reply for agent review
---

# Workflow: Support Ticket Summarizer

Use this workflow to read a support ticket, summarize it, and draft a reply
for a human agent to review before sending.

## Inputs

- `ticket_id`: the support ticket to summarize; required

## Control

- Primary agent: this workflow owns reading the ticket and assembling the
  result.
- Decision model: deterministic — always summarize, always draft a reply.
- Delegation: a Drafting worker produces the reply text.

## Steps

1. Load the operating contract
   - OBEY the support-ticket rules before any other workflow action.

2. Establish the target
   - Read the ticket identified by `ticket_id` in full.

3. Execute the work
   - Summarize the ticket's issue in two or three sentences.
   - Delegate to the Drafting worker to produce a reply.

4. Finish
   - Return the summary and the drafted reply to the caller.

## Stop Conditions

- Stop and report if `ticket_id` does not resolve to a real ticket.
