@infrastructure
Feature: Cloud infrastructure
  Core cloud resources are provisioned and reachable.

  Scenario: Neon database is reachable
    Given a Neon database URL is configured
    Then the database should be reachable on port 5432

  Scenario: Required tables exist in the Neon database
    Given a Neon database URL is configured
    Then the following tables should exist:
      | table      |
      | photos     |
      | tags       |
      | photo_tags |
