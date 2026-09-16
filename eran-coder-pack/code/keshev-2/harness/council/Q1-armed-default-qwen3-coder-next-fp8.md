POSITION: Armed mode should be the default in KESHEV 2.  

REASONS:  
• The 09:46 scar demonstrates that presence gates alone fail catastrophically when the user is *physically present but inactive*—a common dictation state—yet the mic remains dangerously active.  
• The owner’s hands-free workflow *requires* active engagement; defaulting to armed aligns with his preference for intentional control over passive, frictionless typing.  
• Arm timeout (900s) + re-arm every 15 min balances safety with usability: it’s long enough for sustained dictation but short enough to prevent accidental activation during absences.  

RISKS:  
• Slight friction for users who forget to arm (mitigated by clear UI cues and auto-prompt after 30s of idle).  
• Edge cases where user is present but *not* at keyboard (e.g., phone call) may temporarily block dictation—acceptable given the severity of the alternative.  

**Recommended defaults**:  
`enter_idle_limit_s = 60`, `type_idle_limit_s = 180`, `arm_timeout_s = 900`  
*(60s Enter guard prevents burst errors; 180s typing guard allows brief pauses; 900s arm expiry matches proven A behavior.)*