Feature: Tenant isolation
  Two organisations share the platform and must never share data. The promise is
  stronger than "you may not read it": another organisation's records must be
  indistinguishable from records that do not exist, so that nobody can learn what
  the other tenant has by asking about it.

  Scenario Outline: One organisation cannot reach another's <record>
    Given I am signed in as the admin of "acme"
    When I ask for a <record> belonging to "globex"
    Then it appears not to exist
    And its owner can still see it

    Examples:
      | record   |
      | customer |
      | campaign |
