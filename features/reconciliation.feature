@infrastructure
Feature: Pipeline reconciliation records orphans as photo_events
  Periodically diffing S3 and the photos table catches silent drift —
  objects that exist in S3 with no DB row, or DB rows whose S3 object
  was deleted out-of-band. The reconciler writes a photo_events row for
  each orphan so the gap is at least visible in the audit log.

  Scenario: Reconciler records orphan_s3_only for a stray S3 object
    Given a unique JPEG exists in the photos bucket with no corresponding photos row
    When the reconciler runs
    Then a photo_events row with event_type "orphan_s3_only" should exist for the stray s3_key
    And the orphan event actor should be "reconciler"

  Scenario: Reconciler records orphan_db_only for a stray photos row
    Given a unique photos row exists in Neon with no corresponding S3 object
    When the reconciler runs
    Then a photo_events row with event_type "orphan_db_only" should exist for the stray s3_key

  Scenario: Reconciler does not duplicate events on repeat runs
    Given a unique JPEG exists in the photos bucket with no corresponding photos row
    And the reconciler has already run once
    When the reconciler runs again
    Then exactly one "orphan_s3_only" photo_events row should exist for the stray s3_key
