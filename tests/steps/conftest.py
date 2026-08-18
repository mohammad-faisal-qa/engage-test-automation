"""Makes the shared journey steps and fixtures visible to every feature module.

The star import is load-bearing and not a shortcut. pytest-bdd does not decorate
the step function it is given — it registers the definition as a *module-level
attribute* whose name is generated from the step text, e.g.

    pytestbdd_stepdef_given_I am signed in as the {role} of "{tenant}"

Step lookup then scans the test module and its conftests for attributes of that
shape. Importing `signed_in_as` by name therefore brings the function across and
leaves the registration behind, and every scenario fails with
StepDefinitionNotFoundError while the step is plainly defined and imported —
which is a confusing way to spend an afternoon. `import *` copies the generated
names too, because it copies the module dictionary rather than resolving
identifiers.
"""

from steps.common_steps import *  # noqa: F401,F403
