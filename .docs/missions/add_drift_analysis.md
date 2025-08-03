Background:
SafeBreach users use either out-of-the-box or customized scenarios as templates for their security tests.
It is common that a customer would schedule a recurring test based on a given scenario (e.g. Ransomeware susceptability scenario).
A fundamental need for SafeBreach users is to be able to analyze the drift between two different executions of the same test scenario and to identify potential regressions or improvements in the security posture. A drift is defined as a situation where where two simulations that are equivalent in all parameters (like attack id, attacker host, target host, protocol etc) end with different final status. While such two simulations have different simulation ids they can be correlated by the 'drift_tracking_code' attribute on the reduced simulation result entity.
When two or more simulation results share the same 'drift_tracking_code' it means that 100% of the parameters of the simulation were the same and so the rational expectation is that the final results for those would be the same. In the real world there are drifts. The most common cause for drifts is the heuristic behavior of the security controls. Other factors that can impact consistency of the simulation results could sometimes be timing issues, varying loads or conditions on the participating hosts (e.g. having a user logged on the host).

A list of the various types of regressions is manifested in the file safebreach_mcp_data/drifts_metadata.py.

The mission:
- I have started adding support in the safebreach_mcp_data MCP component to make it aware of the drifts in the simulation entity and all the accessor functions to it.
- I added some TODO comments in the code. Your mission is to complete from where i left off. Add them to this mission document.


General guidelines:
- The scope of code changes must be only in the safebreach_mcp_data directory and any of its sub-directories but not above.
- Before starting read all the *.md files in the project and become familiar with the project
- New code must be in full consistency to existing code in the equivalent files in other directories
- Before making any code changes run all the tests to establish a full quality baseline 
- Implement unit tests, integration tests and end to end tests to achieve at least 80% code coverage for all the new code with a focus on covering all the filtering and verbosity options.
- After implementing the code changes run all the tests again to ensure nothing broke
- Update all the relevant md files with respect to the new changes

