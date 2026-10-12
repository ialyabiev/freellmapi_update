"# FreeLLMAPI Updater Agent"  
""  
"## Purpose"  
"Auto-update FreeLLMAPI from GitHub releases with safety checks."  
""  
"## Skill: update_freellmapi"  
"Triggers the updater script."  
""  
"## Manual Run"  
'```powershell'  
"cd `\$PROJECT_ROOT`"  
"uv run python freellmapi_updater.py"  
'```'  
""  
"## Scheduled Run"  
"Use Agnes scheduler to trigger \`update_freellmapi\` skill daily."  
""  
"## Logs"  
'Located at: `logs\freellmapi_update.log` (relative to project root)' 
