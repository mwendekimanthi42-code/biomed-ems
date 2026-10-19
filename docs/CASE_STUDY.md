# Case study: Biomed EMS

> **This is a draft for you to make your own.** Everything in [square brackets] needs your input, and anything that does not sound like you should be rewritten. Keep it honest: describe what you really did, tested, and decided. Aim for one to two pages, with 3 or 4 screenshots.

## Summary

Biomed EMS is a multi-facility web application for managing biomedical equipment: tracking devices, scheduling preventive maintenance, managing repair jobs, and producing audit and budget reports for county health officials. I built it with Python, Flask, and SQLite as a portfolio project, drawing on my [Electrical and Biomedical Engineering] studies, including coursework in hospital engineering management and engineering economics.

**Live demo:** [link] · **Code:** [GitHub link] · **Demo video:** [link]

## The problem

Hospital equipment such as ventilators, monitors, and defibrillators needs regular maintenance, fast repairs, and eventual replacement. When records live in paper files and spreadsheets, three things go wrong: maintenance is missed without anyone noticing, nobody can see which equipment keeps failing, and replacement budgets are guesses. Officials responsible for many facilities have the hardest time, because they can't compare how well different hospitals look after their equipment.

[Add one or two sentences from your own experience, such as a hospital visit, a lecture, or an attachment, if you have one. Do not invent one.]

## Who it is for

| User | What they need |
|---|---|
| Clinical staff | A quick way to report a faulty device |
| Technicians | A clear list of jobs assigned to them |
| Facility engineers | Control of their facility's equipment, jobs, and maintenance schedule |
| County officers | A read-only comparison of facilities, and numbers for audits and budgets |

## What I built

- An **equipment register** with search, filters, device history, lifecycle tracking, and a repair-versus-replacement warning.
- A **work order workflow**: report a fault, assign it, start it, complete it with downtime and cost, with automatic preventive-maintenance job generation.
- A **dashboard** and three **reports** (maintenance audit, replacement budget, reliability) that can be printed or exported as CSV.
- **Role-based access** for five roles, with every query limited to the facilities a user may see.

[Insert screenshots: dashboard, device page, budget report.]

## Design decisions and trade-offs

1. **SQLite with plain SQL.** It keeps the project easy to run and shows the SQL directly. The trade-off is one writer at a time, so a real multi-hospital deployment would move to PostgreSQL. I kept the data access simple so that move would be realistic.
2. **One place decides who sees what.** A single function, `facility_clause()`, limits every query to the user's facilities, so a new page cannot accidentally leak another hospital's data. Records outside a user's scope return "not found", not "forbidden", so their existence isn't revealed.
3. **The database protects the data, not just the code.** For example, a composite foreign key prevents a device from being placed in a department belonging to a different facility, and constraints reject negative costs and invalid statuses.
4. **Devices are decommissioned, never deleted.** Maintenance history has value even after a device is retired.
5. **Rules live on equipment types.** Risk score, maintenance interval, expected life, and replacement cost sit on the type, so every device of that type is treated consistently and one edit updates them all.
6. **Transparent scoring.** The replacement priority score is a weighted sum of age, repair spend, and risk. Every report explains how its numbers are calculated, because a score nobody can explain is not useful for budgeting. The weights and thresholds are my assumptions, adjustable in one place.
7. **Security that is tested.** Passwords are hashed; forms carry CSRF tokens; accounts lock after repeated failed logins; role checks run on the server; and CSV exports are protected against spreadsheet formula injection.

## How I tested it

I wrote 79 automated tests with pytest. They cover permissions and facility scoping for each role, the whole job workflow, report calculations checked against hand-computed answers (for example MTBF and the budget buckets), CSV safety, login lockout, and time-zone display. I also checked every page against a seeded database of about 500 devices and 2,700 work orders, and rehearsed a clean production start-up before deploying.

[Add one real bug you found and fixed, and what you learned from it. For example: a test or a screenshot that showed something wrong.]

## What the data shows

With the fictional demo data, I deliberately made some facilities better at maintenance than others. The facility comparison then shows the difference immediately: [fill in from your dashboard, for example "one hospital keeps about nine in ten devices up to date, while another is at about half"]. The point is that the system makes such differences visible to an official in seconds.

## Limitations

- The data is fictional, and replacement costs and equipment lifespans are my estimates, not real prices or standards.
- MTBF is an approximation, and thresholds such as "review when repairs reach 50% of replacement cost" are rules of thumb.
- SQLite limits how many people can write at once.
- No attachments, email alerts, or barcode scanning, and no formal accessibility audit.

## What I would do next

[Pick the ones you actually care about] Add an admin screen for equipment types and costs; QR-code asset tags; email alerts for overdue maintenance; PostgreSQL support; and validation with a real biomedical engineer.

## What I learned

[Write 3 or 4 sentences in your own voice. Ideas: designing a database around real workflows; why testing permissions matters; turning an engineering economics idea (repair versus replace) into a feature; deploying something you built.]

## How I built it

[Be specific and honest here. This project was built with guidance from an AI assistant, and a short, clear statement of that, plus what you did yourself, is better than leaving it out. For example: "I defined the problem and scope, chose the features, set up and ran the project locally, tested every role, found and reported issues, and wrote this case study. I used an AI assistant for code generation and explanations, and I reviewed the code so I can explain how it works."]
