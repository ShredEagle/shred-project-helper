il semble que publish touch le fichier conan/conanfile.py
devrait pouvoir commit si dirty mais rien de staged
doit s'arreter si le conanfile est dirty
mettre le fichier workspace updater dans le commit de workspace
# SPH workflow
## Load and save config
mostly github access token for the moment
## Connect to github
* connect to github
## Create editables from workspace file
* load workspace file
* create editables from workspace
## Update editable loop
* find editable to update
	* i.e editable that doesn't have any non updated dependency
* Update the editable
	* check state of repo and commit
		* Why check state before update: So that if the only change is the conan file we can commit it automatically
		* Confirm that user wants to commit
		* Commit changes
		* Check active branch is develop
			* if no merge into develop

	* update conan file
	* push to github
	* wait for worlflow to finish
## Update the workspace
* change all dependency sha to new sha (10 first characters right now)