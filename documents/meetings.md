# Project Globe - Meeting Notes

## March 5, 2026 - Sprint Planning

**Attendees:** Sarah Chen, David Park, Noa Levy, Tom Baker

**Agenda:**
- Q1 feature freeze timeline
- Migration to new payment provider
- Hiring update

**Discussion:**
Sarah opened by confirming the Q1 feature freeze is set for March 20. Anything not merged by EOD March 19 rolls to Q2. David raised a concern that the payment provider migration (Stripe to Adyen) won't be ready — the sandbox integration is working but they haven't started on webhook handling yet. Sarah suggested pulling in Noa to help, and Noa agreed she can shift from the dashboard rework starting March 10.

Tom gave a hiring update: two backend candidates in final rounds, one frontend candidate declined the offer citing compensation. Sarah asked Tom to revisit the salary band with HR.

**Action Items:**
- [ ] David: Webhook handler draft PR by March 12
- [ ] Noa: Hand off dashboard tasks to Lisa by March 10
- [ ] Tom: Schedule salary band review with HR by March 7
- [ ] Sarah: Send feature freeze reminder to all-hands Slack

---

## March 12, 2026 - Midpoint Check-in

**Attendees:** Sarah Chen, David Park, Noa Levy

**Agenda:**
- Payment migration progress
- Server stability issues
- Q1 revenue review prep

**Discussion:**
David demoed the webhook handler — basic flow works for payment success and failure events. Refund webhooks are not handled yet, estimated 2 more days. Noa flagged that she found three undocumented webhook event types in Adyen's API that we'll need to handle: CHARGEBACK, CHARGEBACK_REVERSED, and REPORT_AVAILABLE. David was not aware of these.

Sarah raised the server stability issues from last weekend — two outages on Saturday, roughly 45 minutes of downtime total. Root cause was the connection pool exhausting under load. David mentioned he saw this in the logs but didn't escalate because it self-recovered. Sarah stressed that any production outage needs to be reported in #incidents immediately, even if it recovers.

Re: Q1 revenue review — Sarah needs final numbers from the sales team by March 15. She'll compile the deck over the weekend.

**Decisions:**
- Refund webhooks are P1, chargeback handling is P2 (post-freeze)
- Connection pool max increased from 20 to 50 as temporary fix
- David to add alerting on pool utilization > 80%

**Action Items:**
- [ ] David: Refund webhooks by March 14
- [ ] David: Pool utilization alert by March 13
- [ ] Noa: Document all Adyen webhook types in Confluence
- [ ] Sarah: Follow up with sales for Q1 numbers

---

## March 19, 2026 - Pre-Freeze Standup

**Attendees:** Sarah Chen, David Park, Noa Levy, Tom Baker, Lisa Wong

**Agenda:**
- Freeze readiness
- Open PRs
- Q2 planning preview

**Discussion:**
David confirmed the payment migration PR is ready for review — webhook handler covers payment, refund, and partial refund events. Chargeback is deferred to Q2 as agreed. Noa completed the Adyen webhook documentation and also wrote integration tests covering 14 webhook scenarios.

Lisa gave a quick update on the dashboard rework — she picked up where Noa left off and has the new analytics panel working. It's behind a feature flag (DASHBOARD_V2) and she recommends keeping it flagged through Q2 until they get user feedback.

Tom reported that one backend candidate accepted the offer, starting April 7. The other candidate is still deciding.

Sarah previewed Q2 priorities: (1) chargeback handling, (2) dashboard V2 rollout, (3) API rate limiting — several enterprise clients have been hitting us hard and it's affecting other tenants.

**Action Items:**
- [ ] David: Get payment migration PR reviewed and merged by EOD
- [ ] Lisa: Write Q2 plan for dashboard V2 rollout
- [ ] Sarah: Send Q2 priorities doc to leadership by March 21
