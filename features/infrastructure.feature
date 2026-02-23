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

  Scenario: Frontend bucket exists and has website hosting enabled
    Given a frontend bucket name is configured
    Then the bucket should have static website hosting enabled

  Scenario: Frontend is publicly accessible
    Given a frontend bucket name is configured
    Then the website URL should return HTTP 200
