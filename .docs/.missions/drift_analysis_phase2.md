Mission name: Drift analysis phase 2

Background:
The readme.md file as well as other md files in this project explain the concept of drifts in simulations results. This document details the mission to extend the SafeBreach MCP support for drift analysis. Before this mission, the SafeBreach MCP server allows analyzing the drift between a single simulation comparing to the most recent run of the simulation with exact same parameterx set. That comparison may be across two tests that were spawned from different scenrios and having different test names. In reality, most SafeBreach customers are interested in analyzing the drift between two full test runs that manifest the same scenario. Most commonly two such tests would have the same 'name' attribute. To clarify, every test run would always have a unique 'test_id' but many tests can have the same 'name' attribute to indicate they cover the same scenario.
The matchhing of comparable simulations between two test runs is done based on the 'drift_tracking_code' attribute of the simulation.
When comparing the simulations of two test runs there could be 3 sets of simulations:
 - Simulations with 'drift_tracking_code' that exist only in the first test run
 - Simulations with 'drift_tracking_code' that exist only in the second test run
 - Simulations with 'drift_tracking_code' that are shared between the two tests

 The first two types of sets both indicate drifts between the two test runs as they represent simulations that don't have a match in the other test. This would commonly happen if the environmental conditions were not 100% equal during the two test runs. For example, a simulator might not be perfectly healthy in one of the tests.
 The third type of simulations with equal 'drift_tracking_code' between the two test runs is where the more thorough analysis is required to determine if there are drifts. For simulations in this set we need to go over each of the simulation pairs (by the 'drift_tracking_code' value) and compare the 'status' attributes of the simulations from the first and second test run. If the 'status' attribute is equal then there is no drift. if the 'status' is different then there is a drift and we want to call out the exact type of drift per the mapping detailed in the object drift_types_mapping in the file drifts_metadata.py. Our goal is to allow the LLM and Agent operating the MCP server to effectively analyze the drifts between two tests.

The mission:
The mission is to add a new tool to the safebreach_mcp_data server with the name sb_get_test_drifts. The function would take two parameters
 - console (in consistency with all other tools) - this indicates which console hosts the test that we want to analyze
 - the test_id to identify the test run that we want to analyze.

The new tool sb_get_test_drift would apply the following logic:
 - Search for the most recent test with the exact same 'name' preceding (in date) the input test with 'test_id'.
   Searching for tests can be done by calling to 'sb_get_tests_history' with a name_filter parameter and a end_date filter where the end_date filter must be before the end_date of the given test_id. By asking the function to sort the result by the end_date in a descending order it is possible get the desired test_id with a single call without iterating through the pages.
 - Once the baseline test_id is identified in the previous step the list of simulations along with their status and drift_tracking_code can be obtained by calling to sb_get_test_simulations with just the console and test_id parameters. You would need to iterate all the pages to get all the simulations.
 - Use the 'drift_types_mapping' to divide the simulations in the two test runs to the three logical sets as described above
 - Produce an output in the form of:

 {
    "total_drifts": number,    # sums the total number of simulations that are in a state of drift.
                                # This includes all the simulations that are exclusive to either one of the test runs and all the
                                # simulations that have a match in the other test but with a different 'status'.

    "test_id_1": ["sim_id_1", "sim_id_2"...], # array listing the simulation ids that are exclusive to the first test id and don't have
                                               # a matching simulation with 'drift_tracking_code' in the other test

  
    "test_id_2": ["sim_id_3", "sim_id_4"...], # array listing the simulation ids that are exclusive to the second test id and don't have
                                               # a matching simulation with 'drift_tracking_code' in the other test

    "drifts": [
        {
            "drift_tracking_code": drift_tracking_code,
            "drift_from": {
                "simulation_id": "id", # id of the simulation from the first test
                "status": "status of the simulation"
                },
            "drift_to": {
                "simulation_id": "id", # id of the simulation from the first test
                "status": "status of the simulation"
                }
        }
    ] 
                                                                                            
 }


 General guidelines:
- The scope of code changes must be only in the safebreach_mcp_data directory and any of its sub-directories but not above.
- Before starting read all the *.md files in the project and become familiar with the project
- if you have any questions or need any clarifications regarding the mission then ask me before making code changes
- New code must be in full consistency to existing code in the equivalent files in other directories
- Before making any code changes run all the tests to establish a full quality baseline 
- Implement unit tests, integration tests and end to end tests to achieve at least 80% code coverage for all the new code with a focus on covering all the filtering and verbosity options.
- After implementing the code changes run all the tests again to ensure nothing broke
