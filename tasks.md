# Tasks

## Upload bucket

- [ ] Handle stuck objects in the upload bucket — photos that landed there but were never processed (e.g. image handler Lambda failed mid-way). Options: S3 lifecycle expiry rule, or a manual cleanup script that deletes objects older than N days.
- [ ] When a stats page alert is going off, if should display the problem record(s) in the information tooltip. 
- [ ] Allow multi-select on the galleries to allow archiving or processing multiple photos at once
- [ ] Better traceability around the photo lifecycle. Once a photo enters the system, we should be able to see it progressing through its entire lifecycle.
- [ ] Archived photos gallery that allows photos to be moved back to the inbox/gallery