# Demo video script (about 2.5 minutes)

**Setup:** use the live link or run locally with a freshly seeded database. Browser at 100% zoom, bookmarks bar hidden, one window. Record with Windows Game Bar (Win + G) or OBS. Speak slowly; you can trim afterwards.

| Time | On screen | Say (in your own words) |
|---|---|---|
| 0:00 | Login page | "This is Biomed EMS, a system I built to manage medical equipment across several hospitals. It's for hospital engineers, but also county officials who audit maintenance and plan budgets. The data is fictional." |
| 0:15 | Log in as the **nurse** (`nurse1.rcrh@example.com`). Open a device, click **Report fault**, describe a fault, choose "Not working at all". | "A nurse can only report problems. When she says the device isn't working, its status changes automatically." |
| 0:40 | Log in as the **engineer** (`engineer.rcrh@example.com`). Open **Work orders**, open the new job, assign a technician. | "The facility engineer sees the new job straight away and assigns it to a technician." |
| 1:00 | Log in as the **technician** (`tech1.rcrh@example.com`). **Assigned to me**, start the job, complete it with notes, downtime, and cost. | "The technician records what was done, how long the device was down, and the cost. That data feeds every report." |
| 1:25 | Back to the device page: show status, history, lifecycle bar, and the replacement banner on a heavily repaired device. | "The device page now shows its full history, how much of its life is used, and warns when repairs cost nearly half the price of a new one." |
| 1:45 | Log in as the **county officer** (`officer.nairobi@example.com`). Dashboard: point to the facility comparison. | "A county officer sees every facility in their county, read-only. Here they can compare how well each hospital maintains its equipment." |
| 2:05 | **Reports**: open the audit report, then the budget report, click **Download CSV**. | "Reports can be printed or downloaded. The budget report ranks devices for replacement with a score I explain on the page, and estimates what it would cost." |
| 2:25 | README or GitHub page | "It's built with Flask and SQLite, has 79 automated tests, and enforces who can see which facility's data on the server. The code is on GitHub." |

**Tips**
- Rehearse once without recording. The first take is usually rushed.
- If a click takes long on free hosting, trim it out.
- Mention one limitation honestly (for example, replacement costs are placeholders). It makes you more credible, not less.
- Keep the video under 3 minutes and put it at the top of your portfolio page.
