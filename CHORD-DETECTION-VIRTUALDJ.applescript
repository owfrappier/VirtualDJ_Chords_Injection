-- VDJ CHORD INJECTOR V13 DUP CLEAN

use AppleScript version "2.8"
use scripting additions

property pythonBin : "/Users/" & (short user name of (system info)) & "/.venvs/audio312/bin/python"
property POI_COLOR : "4294967295"

on detectExternalVDJDatabase()
	set foundPaths to {}
	set volList to paragraphs of (do shell script "find /Volumes -maxdepth 2 -path '*/VirtualDJ/database.xml' -type f 2>/dev/null")
	
	repeat with p in volList
		if p is not "" then set end of foundPaths to p
	end repeat
	
	return foundPaths
end detectExternalVDJDatabase

on run
	try
		-- Close VirtualDJ if running
		tell application "System Events"
			if exists process "VirtualDJ" then
				tell application "VirtualDJ" to quit
				delay 2
			end if
		end tell
		
		-- Detect external VirtualDJ database
		set detectedDBs to detectExternalVDJDatabase()
		
		if (count of detectedDBs) is 1 then
			set dbPath to item 1 of detectedDBs
			set useDetected to button returned of (display dialog "External VirtualDJ database detected:" & return & return & dbPath & return & return & "Use this database?" buttons {"Choose manually", "Use detected"} default button "Use detected")
			
			if useDetected is "Choose manually" then
				set dbFile to choose file with prompt "Select VirtualDJ clean database.xml:"
				set dbPath to POSIX path of dbFile
			end if
			
		else if (count of detectedDBs) > 1 then
			display dialog "Warning: multiple external VirtualDJ databases detected. Please choose the correct database manually." buttons {"OK"} with icon caution
			set dbFile to choose file with prompt "Select VirtualDJ clean database.xml:"
			set dbPath to POSIX path of dbFile
			
		else
			set dbFile to choose file with prompt "Select VirtualDJ clean database.xml:"
			set dbPath to POSIX path of dbFile
		end if
		
		set modeChoice to button returned of (display dialog "Analysis mode:" buttons {"Full folder", "Single file", "Filter by first letter"} default button "Full folder")
		
		set reanalyseChoice to button returned of (display dialog "Re-analyze tracks that already have chords?" buttons {"No", "Yes"} default button "No")
		
		if reanalyseChoice is "Yes" then
			set reanalyseFlag to "1"
		else
			set reanalyseFlag to "0"
		end if
		
		set searchWord to ""
		set firstLetter to ""
		
		if modeChoice is "Single file" then
			set audioItem to choose file with prompt "Select audio file to analyze:"
			set audioPath to POSIX path of audioItem
			
		else if modeChoice is "Filter by first letter" then
			set audioFolder to choose folder with prompt "Select audio folder:"
			set audioPath to POSIX path of audioFolder
			set firstLetter to text returned of (display dialog "Enter first letter filter:" default answer "")
			
		else
			set audioFolder to choose folder with prompt "Select audio folder to analyze:"
			set audioPath to POSIX path of audioFolder
		end if
		
		set workDir to do shell script "/usr/bin/dirname " & quoted form of dbPath
		set scriptPath to POSIX path of (path to me)
		set scriptDir to do shell script "/usr/bin/dirname " & quoted form of scriptPath
		
		set pyPath to scriptDir & "/vdj_Chords_Analyse.py"
		set cachePath to workDir & "/Data.xml"
		set backupPath to dbPath & ".backup-v13-" & (do shell script "date +%Y%m%d-%H%M%S")
		
		do shell script "/bin/cp -p " & quoted form of dbPath & " " & quoted form of backupPath
		
		set cmd to quoted form of pythonBin & " " & quoted form of pyPath & " " & quoted form of dbPath & " " & quoted form of audioPath & " " & quoted form of cachePath & " " & quoted form of POI_COLOR & " " & quoted form of searchWord & " " & reanalyseFlag & " " & quoted form of firstLetter
		
		set fullCmd to "echo 'VDJ CHORD ANALYSIS V13 - Ctrl+C to STOP' ; " & cmd
		
		tell application "Terminal"
			activate
			do script fullCmd
		end tell
		
	on error errMsg number errNum
		display dialog "Error (" & errNum & "): " & errMsg buttons {"OK"} with icon stop
	end try
end run