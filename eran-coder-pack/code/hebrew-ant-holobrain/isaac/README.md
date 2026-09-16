# Isaac Sim integration boundary

Isaac Sim is not currently installed on Eran1-Eran4. Do not claim simulator
training until an installation, compatibility check, rendered sensor episode,
and policy update are all verified.

Planned observation packet:

```json
{
  "schema": "holobrain.isaac.episode/1",
  "episode_id": "uuid",
  "sim_seed": 0,
  "camera_rgb": "array reference",
  "contact_forces": "array reference",
  "imu": "array reference",
  "joint_state": "array reference",
  "action": "array reference",
  "reward_components": {},
  "termination": "string"
}
```

Start with a bounded Isaac Lab task and a simulated body. Physical actuation is
a later, separately authorized safety gate.
