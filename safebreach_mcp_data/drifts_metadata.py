'''
This file contains metadata about how to interpret drifts in simulation results.
It maps different types of drifts to their descriptions, security impacts, and hints for further investigation
'''
drift_types_mapping = {
    "result_improvement": {
        "type_of_drift": "from_no_result_to_result",
        "security_impact": "neutral",
        "description": "Former simulation execution had no result due to failure but latter has a result",
        "hint_to_llm": "the \'result_code\' field in the former simulation result entity may contain more details about the failure"
    },
    "fail-internal_fail": {
        "type_of_drift": "from_blocked_to_no_result",
        "security_impact": "neutral",
        "description": "Former simulation was blocked. Internal failure during latter simulation execution",
        "hint_to_llm": "the \'result_code\' field in the latter simulation result entity may contain more details about the failure"
    },
    "success-internal_fail": {
        "type_of_drift": "from_not_blocked_to_no_result",
        "security_impact": "neutral",
        "description": "Former simulation was not blocked. Internal failure during latter simulation execution",
        "hint_to_llm": "the \'result_code\' field in the latter simulation result entity may contain more details about the failure"
    },
    "success-fail": {
        "type_of_drift": "from_not_blocked_to_blocked",
        "security_impact": "positive",
        "description": "Former simulation was not blocked. Latter simulation was blocked",
        "hint_to_llm": "Check the simulation logs and correlated security control events to explain why the latter was blocked"
    },
    "prevented-stopped": {
        "type_of_drift": "from_prevented_to_stopped",
        "security_impact": "negative",
        "description": "Former simulation was prevented. Latter simulation was stopped",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was not reported by the security control as prevented"
    },
    "stopped-prevented": {
        "type_of_drift": "from_stopped_to_prevented",
        "security_impact": "positive",
        "description": "Former simulation was stopped. Latter simulation was prevented.",
        "hint_to_llm": "Check the correlated security control events to determine why the former was not reported by the security control as prevented"
    },
    "fail-success": {
        "type_of_drift": "from_blocked_to_not-blocked",
        "security_impact": "negative",
        "description": "Former simulation was blocked. Latter simulation was not blocked",
        "hint_to_llm": "Check the simulation logs to determine why the former simulation was blocked and the latter was not"
    },
    "logged-detected": {
        "type_of_drift": "from_logged_to_detected",
        "security_impact": "positive",
        "description": "Former simulation was only logged by the security control. Latter simulation was reported as detected",
        "hint_to_llm": "Check the correlated security control events to determine why the former was not reported as detected"
    },
    "inconsistent-missed": {
        "type_of_drift": "from_inconsistent_to_not_blocked",
        "security_impact": "positive",
        "description": "Former simulation was potentially falsely declared by the security control as prevented while it was not really blocked. Latter simulation was just not blocked",
        "hint_to_llm": "Check the correlated security control events to determine why the former was reported by the security control as prevented as it could be a false positive"
    },
    "detected-logged": {
        "type_of_drift": "from_detected_to_logged",
        "security_impact": "negative",
        "description": "Former simulation was reported as detected by the security control. Latter simulation was only logged",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was not reported as detected"
    },
    "logged-missed": {
        "type_of_drift": "from_logged_to_missed",
        "security_impact": "negative",
        "description": "Former simulation was not blocked by logged by the security control. Latter simulation was not blocked and not logged",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was not logged"
    },
    "missed-logged": {
        "type_of_drift": "from_missed_to_logged",
        "security_impact": "positive",
        "description": "Former simulation was not blocked and not logged by the security control. Latter simulation was logged",
        "hint_to_llm": "Check the correlated security control events to determine why the former was not logged"
    },
    "missed-inconsistent": {
        "type_of_drift": "from_missed_to_inconsistent",
        "security_impact": "negative",
        "description": "Former simulation was not blocked and not logged by the security control. Latter simulation was potentially falsely declared as prevented by the security control",
        "hint_to_llm": "Check the correlated security control events to determine why the the latter was reported as prevented as it could be a false positive"
    },
    "logged-inconsistent": {
        "type_of_drift": "from_logged_to_inconsistent",
        "security_impact": "negative",
        "description": "Former simulation was not blocked and logged by the security control. Latter simulation was potentially falsely declared as prevented by the security control",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was reported as prevented as it could be a false positive"
    },
    "detected-inconsistent": {
        "type_of_drift": "from_detected_to_inconsistent",
        "security_impact": "negative",
        "description": "Former simulation was reported as detected by the security control. Latter simulation was potentially falsely declared as prevented by the security control",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was reported as prevented as it could be a false positive"
    },
    "inconsistent-logged": {
        "type_of_drift": "from_inconsistent_to_logged",
        "security_impact": "positive",
        "description": "Former simulation was potentially falsely declared as prevented by the security control. Latter simulation was logged",
        "hint_to_llm": "Check the correlated security control events to determine if the former was a false positive or the latter was a false negative"
    },
    "inconsistent-detected": {
        "type_of_drift": "from_inconsistent_to_detected",
        "security_impact": "positive",
        "description": "Former simulation was potentially falsely declared as prevented by the security control. Latter simulation was reported as detected",
        "hint_to_llm": "Check the correlated security control events to determine if the former was a false positive or the latter was a false negative"
    },
    "missed-detected": {
        "type_of_drift": "from_missed_to_detected",
        "security_impact": "positive",
        "description": "Former simulation was not blocked and not logged by the security control. Latter simulation was reported as detected",
        "hint_to_llm": "Check the correlated security control events to determine why the former was not logged or detected"
    }
    }