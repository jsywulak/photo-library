@infrastructure
Feature: Async Lambda failures land in the DLQ
  When EventBridge or another async invoker calls a Lambda and the Lambda
  raises an exception after its retry budget is exhausted, the trigger event
  is captured in an SQS Dead-Letter Queue so the work isn't silently lost.

  Scenario: Processor v2 async failures land in the DLQ
    Given the processor v2 Lambda's DLQ is reachable
    When the processor v2 Lambda is invoked async with a payload that causes it to error
    Then a message should arrive on the processor v2 DLQ within 90 seconds
    And the DLQ message body should reference the failing payload marker
