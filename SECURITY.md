# Security policy

Report a vulnerability privately using this repository's GitHub private vulnerability reporting feature when available, or privately to the repository owner. Do not put secrets, full private prompts, credentials or unredacted vendor logs in issues.

This provider is an unofficial local integration, not a security sandbox or authorization to use OpenCode. OpenCode itself and any user-configured vendor plugins/hooks remain trusted executable code. Workspace denial rules, protocol refusals and validation are defense in depth, not an OS isolation boundary.

The intended boundaries are:

- No direct credential-store access by plugin code, no arbitrary parent credential inheritance, and no client impersonation.
- No automatic permission approvals or execution of model-supplied shell commands by the bridge.
- No inference on an unconfirmed, unadvertised or unapproved model.
- No direct dispatch of OpenCode-native tool calls; remote tool calls must match Hermes's supplied tool inventory and choice.
- No private Hermes imports, runtime monkey-patches, self-updater or telemetry.
- Cancellation and timeout clean up the plugin's own transport; unrelated user processes are not targeted.

Use the included offline tests to reproduce issues without exposing private model inputs. Consult README.md for data flow, subprocess/environment behavior, platform verification and known limits.
