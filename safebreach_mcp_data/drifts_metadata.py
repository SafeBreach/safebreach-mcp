'''
This file contains metadata about how to interpret drifts in simulation results.
It maps different types of drifts to their descriptions, security impacts, and hints for further investigation
'''
drift_types_mapping = {
    "result_improvement": {
        "type_of_drift": "from_no_result_to_result",
        "security_impact": "neutral",
        "description": "Former simulation execution had no result due to failure but latter has a result",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The 'result_code' field may contain more details about the failure"
    },
    "fail-no_result": {
        "type_of_drift": "from_blocked_to_no_result",
        "security_impact": "neutral",
        "description": "Former simulation was blocked. Internal failure during latter simulation execution",
        "hint_to_llm": "Check the latter simulation logs and security events to understand what caused the execution failure. The 'result_code' field may contain more details about the failure"
    },
    "success-no_result": {
        "type_of_drift": "from_not_blocked_to_no_result",
        "security_impact": "neutral",
        "description": "Former simulation was not blocked. Internal failure during latter simulation execution",
        "hint_to_llm": "Check the latter simulation logs and security events to understand what caused the execution failure. The 'result_code' field may contain more details about the failure"
    },
    "success-fail": {
        "type_of_drift": "from_not_blocked_to_blocked",
        "security_impact": "positive",
        "description": "Former simulation was not blocked. Latter simulation was blocked",
        "hint_to_llm": "If needed to explain the improvement, check the simulation logs and correlated security control events to explain why the former was not blocked and the latter was blocked"
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
        "hint_to_llm": "If needed to explain the improvement, check the correlated security control events to determine why the former was not reported by the security control as prevented"
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
        "description": "Former simulation was not blocked but only logged by the security control. Latter simulation was not blocked but reported as detected",
        "hint_to_llm": "If needed to explain the improvement, check the correlated security control events to determine why the former was not reported as detected"
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
        "description": "Former simulation was not blocked but reported as detected by the security control. Latter simulation was not blocked but only logged",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was not reported as detected"
    },
    "logged-missed": {
        "type_of_drift": "from_logged_to_missed",
        "security_impact": "negative",
        "description": "Former simulation was not blocked but logged by the security control. Latter simulation was not blocked and not logged",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was not logged"
    },
    "missed-logged": {
        "type_of_drift": "from_missed_to_logged",
        "security_impact": "positive",
        "description": "Former simulation was not blocked and not logged by the security control. Latter simulation was not blocked but logged",
        "hint_to_llm": "If needed to explain the improvement, check the correlated security control events to determine why the former was not logged"
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
        "description": "Former simulation was not blocked but reported as detected by the security control. Latter simulation was potentially falsely declared as prevented by the security control",
        "hint_to_llm": "Check the correlated security control events to determine why the latter was reported as prevented as it could be a false positive"
    },
    "inconsistent-logged": {
        "type_of_drift": "from_inconsistent_to_logged",
        "security_impact": "positive",
        "description": "Former simulation was potentially falsely declared as prevented by the security control. Latter simulation was not blocked but logged",
        "hint_to_llm": "Check the correlated security control events to determine if the former was a false positive or the latter was a false negative"
    },
    "inconsistent-detected": {
        "type_of_drift": "from_inconsistent_to_detected",
        "security_impact": "positive",
        "description": "Former simulation was potentially falsely declared as prevented by the security control. Latter simulation was not blocked but reported as detected",
        "hint_to_llm": "If needed to explain the improvement, check the correlated security control events to determine if the former was a false positive or the latter was a false negative"
    },
    "missed-detected": {
        "type_of_drift": "from_missed_to_detected",
        "security_impact": "positive",
        "description": "Former simulation was not blocked and not logged by the security control. Latter simulation was not blocked but reported as detected",
        "hint_to_llm": "If needed to explain the improvement, check the correlated security control events to determine why the former was not logged or detected"
    },
    
    # === no_result TRANSITIONS ===
    # no_result to blocking statuses (positive security impact)
    "no_result-prevented": {
        "type_of_drift": "from_no_result_to_prevented",
        "security_impact": "positive",
        "description": "Former simulation had no result due to execution failure. Latter simulation was prevented by security control",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The latter simulation shows the actual security posture"
    },
    "no_result-stopped": {
        "type_of_drift": "from_no_result_to_stopped",
        "security_impact": "positive", 
        "description": "Former simulation had no result due to execution failure. Latter simulation was stopped by security control",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The latter simulation shows the actual security posture"
    }, # fail == stopped
    "no_result-fail": {
        "type_of_drift": "from_no_result_to_stopped",
        "security_impact": "positive", 
        "description": "Former simulation had no result due to execution failure. Latter simulation was stopped by security control",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The latter simulation shows the actual security posture"
    },
    # no_result to missed, logged, detected (negative - now we know there's a security gap)
    "no_result-detected": {
        "type_of_drift": "from_no_result_to_detected",
        "security_impact": "positive",
        "description": "Former simulation had no result due to execution failure. Latter simulation was not blocked but detected by security control",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The latter simulation shows the actual security posture"
    },
    "no_result-logged": {
        "type_of_drift": "from_no_result_to_logged",
        "security_impact": "positive",
        "description": "Former simulation had no result due to execution failure. Latter simulation was not blocked but logged by security control",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The latter simulation shows the actual security posture"
    },
    "no_result-missed": {
        "type_of_drift": "from_no_result_to_missed",
        "security_impact": "negative",
        "description": "Former simulation had no result due to execution failure. Latter simulation was missed by security controls",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The latter simulation reveals a security gap"
    }, # success == missed
      "no_result-success": {
        "type_of_drift": "from_no_result_to_missed",
        "security_impact": "negative",
        "description": "Former simulation had no result due to execution failure. Latter simulation was missed by security controls",
        "hint_to_llm": "Check the former simulation logs and security events to understand what caused the execution failure. The latter simulation reveals a security gap"
    },
    
    # === REVERSE no_result TRANSITIONS (negative - losing visibility) ===
    "prevented-no_result": {
        "type_of_drift": "from_prevented_to_no_result",
        "security_impact": "negative",
        "description": "Former simulation was prevented by security control. Latter simulation failed to execute",
        "hint_to_llm": "Check the latter simulation logs and security events to understand what caused the execution failure. The former simulation shows the actual security posture"
    },
    "stopped-no_result": {
        "type_of_drift": "from_stopped_to_no_result", 
        "security_impact": "negative",
        "description": "Former simulation was stopped by security control. Latter simulation failed to execute",
        "hint_to_llm": "Check the latter simulation logs and security events to understand what caused the execution failure. The former simulation shows the actual security posture"
    },
    "detected-no_result": {
        "type_of_drift": "from_detected_to_no_result",
        "security_impact": "negative", 
        "description": "Former simulation was not blocked but detected by security control. Latter simulation failed to execute",
        "hint_to_llm": "Check the latter simulation logs and security events to understand what caused the execution failure. The former simulation shows the actual security posture"
    },
    "logged-no_result": {
        "type_of_drift": "from_logged_to_no_result",
        "security_impact": "negative",
        "description": "Former simulation was not blocked but logged by security control. Latter simulation failed to execute", 
        "hint_to_llm": "Check the latter simulation logs and security events to understand what caused the execution failure. The former simulation shows the actual security posture"
    },
    "missed-no_result": {
        "type_of_drift": "from_missed_to_no_result",
        "security_impact": "neutral",
        "description": "Former simulation was missed by security controls. Latter simulation failed to execute",
        "hint_to_llm": "Check the latter simulation logs and security events to understand what caused the execution failure. No change in security posture"
    },
    
    # === ADDITIONAL MISSING TRANSITIONS ===
    # Up the hierarchy (positive security impact)
    "missed-stopped": {
        "type_of_drift": "from_missed_to_stopped",
        "security_impact": "positive",
        "description": "Former simulation was missed by security controls. Latter simulation was stopped",
        "hint_to_llm": "If needed to explain the improvement, check the simulation logs and correlated security control events to explain why the former was missed and the latter was stopped"
    },
    "missed-prevented": {
        "type_of_drift": "from_missed_to_prevented", 
        "security_impact": "positive",
        "description": "Former simulation was missed by security controls. Latter simulation was prevented",
        "hint_to_llm": "If needed to explain the improvement, check the simulation logs and correlated security control events to explain why the former was missed and the latter was prevented"
    },
    "logged-stopped": {
        "type_of_drift": "from_logged_to_stopped",
        "security_impact": "positive",
        "description": "Former simulation was not blocked but logged by security control. Latter simulation was stopped",
        "hint_to_llm": "If needed to explain the improvement, check the simulation logs and correlated security control events to explain why the former was logged and the latter was stopped"
    },
    "logged-prevented": {
        "type_of_drift": "from_logged_to_prevented",
        "security_impact": "positive", 
        "description": "Former simulation was not blocked but logged by security control. Latter simulation was prevented",
        "hint_to_llm": "If needed to explain the improvement, check for differences in the simulations logs and correlated security control events to explain why the former was logged and the latter was prevented"
    },
    "detected-stopped": {
        "type_of_drift": "from_detected_to_stopped",
        "security_impact": "positive",
        "description": "Former simulation was not blocked but detected by security control. Latter simulation was stopped", 
        "hint_to_llm": "If needed to explain the improvement, check the latter simulation logs and correlated security control events to explain why the former was detected and the latter was stopped"
    },
    "detected-prevented": {
        "type_of_drift": "from_detected_to_prevented",
        "security_impact": "positive",
        "description": "Former simulation was not blocked but detected by security control. Latter simulation was prevented",
        "hint_to_llm": "If needed to explain the improvement, check security control configuration changes that enabled prevention"
    },
    "stopped-detected": {
        "type_of_drift": "from_stopped_to_detected", 
        "security_impact": "negative",
        "description": "Former simulation was stopped by security control. Latter simulation was not blocked but only detected",
        "hint_to_llm": "If needed to explain the degradation, check both the simulation logs and correlated security control events to explain why the former was blocked and the latter was not blocked and detected"
    },
    "prevented-detected": {
        "type_of_drift": "from_prevented_to_detected",
        "security_impact": "negative",
        "description": "Former simulation was prevented by security control. Latter simulation was not blocked but only detected", 
        "hint_to_llm": "If needed to explain the degradation, check both the simulation logs and correlated security control events to explain why the former was blocked and the latter was not blocked and detected"
    },
    "prevented-logged": {
        "type_of_drift": "from_prevented_to_logged",
        "security_impact": "negative",
        "description": "Former simulation was prevented by security control. Latter simulation was not blocked but only logged",
        "hint_to_llm": "Security posture significantly degraded - attack moved from prevention to logging only. Check if security controls were disabled"
    },
    "prevented-missed": {
        "type_of_drift": "from_prevented_to_missed",
        "security_impact": "negative", 
        "description": "Former simulation was prevented by security control. Latter simulation was missed",
        "hint_to_llm": "Security posture severely degraded - attack moved from prevention to completely missed. Check if security controls were disabled or bypassed"
    },
    "stopped-logged": {
        "type_of_drift": "from_stopped_to_logged",
        "security_impact": "negative",
        "description": "Former simulation was stopped by security control. Latter simulation was not blocked but only logged",
        "hint_to_llm": "Security posture degraded - attack moved from blocking to logging only. Check if security controls were modified or disabled"
    },
    "stopped-missed": {
        "type_of_drift": "from_stopped_to_missed", 
        "security_impact": "negative",
        "description": "Former simulation was stopped by security control. Latter simulation was missed",
        "hint_to_llm": "If needed to explain the degradation, compare the simulation logs and correlated security control events to explain why the former was blocked and the latter was not blocked and missed"
    },
    "detected-missed": {
        "type_of_drift": "from_detected_to_missed",
        "security_impact": "negative",
        "description": "Former simulation was not blocked but detected by security control. Latter simulation was not blocked and missed",
        "hint_to_llm": "if needed to explain the degradation, check the simulation logs and correlated security control events to explain why the former was detected and the latter was not blocked and missed"
    }
    }