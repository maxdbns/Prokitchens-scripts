# Zapier for Inbound Leads — Quick Summary

**Context**: We need to automatically push inbound Gmail emails into Salesforce (upsert: update if the lead exists, create if it doesn't). Volume is about 100 emails/month.

**Zapier can do it.** The Zap would be: Gmail trigger → Search lead in SF → Path → Create or Update. Each email uses 2 Zapier tasks (search + create/update), so ~200 tasks/month. The Pro plan at ~18 €/month includes 750 tasks, so we're good with plenty of margin.

**Watch out for**: SF Duplicate Rules can block API record creation (needs a one-time config tweak from the SF admin). Also, Zapier is not great at parsing structured data from email bodies — if we need that later, Make would be better suited.

**Alternatives considered**: Make (a bit cheaper, better data parsing), n8n (has native SF upsert but needs DevOps to host), Workato/Tray.io (way too expensive, 9k+ €/year), native SF Email Services (needs Apex dev). At our volume the price gap is small, and Zapier is the simplest to set up and maintain.

**Recommendation**: Go with Zapier Pro (~18 €/month). Monitor task usage in case volume grows.
