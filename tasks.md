# Tasks

## Upload bucket

- [ ] Handle stuck objects in the upload bucket — photos that landed there but were never processed (e.g. image handler Lambda failed mid-way). Options: S3 lifecycle expiry rule, or a manual cleanup script that deletes objects older than N days.
- [ ] When a stats page alert is going off, if should display the problem record(s) in the information tooltip. 