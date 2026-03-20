#/***************************************************************************
# GlobalInspectionTiles
#
# This plugin is for classifying samples of pastures areas.
#							 -------------------
#		begin				: 2022-06-20
#		git sha				: $Format:%H$
#		copyright			: (C) 2022 by Tharles de Sousa Andrade | LAPIG - UFG
#		email				: irtharles@gmail.com
# ***************************************************************************/
#
#/***************************************************************************
# *																		 *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU General Public License as published by  *
# *   the Free Software Foundation; either version 2 of the License, or	 *
# *   (at your option) any later version.								   *
# *																		 *
# ***************************************************************************/

#################################################
# Edit the following to match your sources lists
#################################################

# Add iso code for any locales you want to support here (space separated)
# default is no locales
# LOCALES = af
LOCALES =

# If locales are enabled, set the name of the lrelease binary on your system.
#LRELEASE = lrelease
#LRELEASE = lrelease-qt4

# translation
SOURCES = \
	__init__.py \
	qgis_fgi_plugin.py qgis_fgi_plugin_dockwidget.py

PLUGINNAME = global_inspection

# Root-level Python files
PY_FILES = \
	__init__.py \
	qgis_fgi_plugin.py \
	qgis_fgi_plugin_dockwidget.py \
	resources.py

UI_FILES = qgis_fgi_plugin_dockwidget_base.ui

EXTRAS = metadata.txt icon.png

# Subdirectories required by the plugin at runtime
EXTRA_DIRS = src sources config datasource img

COMPILED_RESOURCE_FILES = resources.py

PEP8EXCLUDE=pydev,resources.py,conf.py,third_party,ui

# QGISDIR points to the location where your plugin should be installed.
# This is a path relative to HOME (no leading ~ or /).
#   Linux:   .local/share/QGIS/QGIS3/profiles/default/python/plugins
#   Mac:     Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins
#   Windows: AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins
QGISDIR = .local/share/QGIS/QGIS3/profiles/default/python/plugins

#################################################
# Normally you would not need to edit below here
#################################################

PLUGINDIR = $(HOME)/$(QGISDIR)/$(PLUGINNAME)

HELP = help/build/html

PLUGIN_UPLOAD = $(CURDIR)/plugin_upload.py

RESOURCE_SRC=$(shell grep '^ *<file' resources.qrc | sed 's@</file>@@g;s/.*>//g' | tr '\n' ' ')

.PHONY: default compile test deploy dclean derase zip package upload \
        transup transcompile transclean clean doc pylint pep8 help

default:
	@echo "Available targets:"
	@echo "  make compile       - Compile Qt resources (pyrcc5)"
	@echo "  make deploy        - Deploy plugin to local QGIS plugins directory"
	@echo "  make test          - Run test suite with nosetests"
	@echo "  make zip           - Deploy + create zip bundle"
	@echo "  make package       - Create zip via git archive (VERSION=tag required)"
	@echo "  make clean         - Remove compiled resources"
	@echo "  make pylint        - Run pylint"
	@echo "  make pep8          - Run PEP8 checks"
	@echo "  make doc           - Build Sphinx documentation"
	@echo "  make derase        - Remove deployed plugin"

compile: $(COMPILED_RESOURCE_FILES)

%.py : %.qrc $(RESOURCES_SRC)
	pyrcc5 -o $*.py  $<

%.qm : %.ts
	$(LRELEASE) $<

test: compile transcompile
	@echo
	@echo "----------------------"
	@echo "Regression Test Suite"
	@echo "----------------------"
	@# Preceding dash means that make will continue in case of errors
	@-export PYTHONPATH=`pwd`:$(PYTHONPATH); \
		export QGIS_DEBUG=0; \
		export QGIS_LOG_FILE=/dev/null; \
		nosetests -v --with-id --with-coverage --cover-package=. \
		3>&1 1>&2 2>&3 3>&- || true
	@echo "----------------------"
	@echo "If you get a 'no module named qgis.core' error, try sourcing"
	@echo "the helper script we have provided first then run make test."
	@echo "e.g. source scripts/run-env-linux.sh <path to qgis install>; make test"
	@echo "----------------------"

deploy: compile transcompile
	@echo
	@echo "----------------------------------------------"
	@echo "Deploying plugin to $(PLUGINDIR)"
	@echo "----------------------------------------------"
	mkdir -p $(PLUGINDIR)
	cp -vf $(PY_FILES) $(PLUGINDIR)/
	cp -vf $(UI_FILES) $(PLUGINDIR)/
	cp -vf $(EXTRAS) $(PLUGINDIR)/
	@# Copy subdirectories
	@for DIR in $(EXTRA_DIRS); do \
		echo "Copying $$DIR/ ..."; \
		cp -rf $$DIR $(PLUGINDIR)/; \
	done
	@# Copy i18n if it exists and has content
	@if [ -d i18n ] && [ "$$(ls -A i18n 2>/dev/null)" ]; then \
		cp -rf i18n $(PLUGINDIR)/; \
	fi
	@# Copy help if built
	@if [ -d "$(HELP)" ]; then \
		mkdir -p $(PLUGINDIR)/help; \
		cp -rf $(HELP)/* $(PLUGINDIR)/help/; \
	fi
	@echo "----------------------------------------------"
	@echo "Plugin deployed successfully."
	@echo "----------------------------------------------"

# Remove compiled python files from deployed plugin directory
dclean:
	@echo
	@echo "-----------------------------------"
	@echo "Removing any compiled python files."
	@echo "-----------------------------------"
	find $(PLUGINDIR) -iname "*.pyc" -delete
	find $(PLUGINDIR) -iname "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find $(PLUGINDIR) -iname ".git" -prune -exec rm -Rf {} \;

derase:
	@echo
	@echo "-------------------------"
	@echo "Removing deployed plugin."
	@echo "-------------------------"
	rm -Rf $(PLUGINDIR)

zip: deploy dclean
	@echo
	@echo "---------------------------"
	@echo "Creating plugin zip bundle."
	@echo "---------------------------"
	rm -f $(PLUGINNAME).zip
	cd $(HOME)/$(QGISDIR) && zip -9r $(CURDIR)/$(PLUGINNAME).zip $(PLUGINNAME)
	@echo "Created: $(PLUGINNAME).zip"

package: compile
	# Create a zip package of the plugin named $(PLUGINNAME).zip.
	# This requires use of git (your plugin development directory must be a
	# git repository).
	# To use, pass a valid commit or tag as follows:
	#   make package VERSION=Version_0.3.2
	@echo
	@echo "------------------------------------"
	@echo "Exporting plugin to zip package.	"
	@echo "------------------------------------"
	rm -f $(PLUGINNAME).zip
	git archive --prefix=$(PLUGINNAME)/ -o $(PLUGINNAME).zip $(VERSION)
	@echo "Created package: $(PLUGINNAME).zip"

upload: zip
	@echo
	@echo "-------------------------------------"
	@echo "Uploading plugin to QGIS Plugin repo."
	@echo "-------------------------------------"
	$(PLUGIN_UPLOAD) $(PLUGINNAME).zip

transup:
	@echo
	@echo "------------------------------------------------"
	@echo "Updating translation files with any new strings."
	@echo "------------------------------------------------"
	@chmod +x scripts/update-strings.sh
	@scripts/update-strings.sh $(LOCALES)

transcompile:
	@echo
	@echo "----------------------------------------"
	@echo "Compiled translation files to .qm files."
	@echo "----------------------------------------"
	@chmod +x scripts/compile-strings.sh
	@scripts/compile-strings.sh $(LRELEASE) $(LOCALES)

transclean:
	@echo
	@echo "------------------------------------"
	@echo "Removing compiled translation files."
	@echo "------------------------------------"
	rm -f i18n/*.qm

clean:
	@echo
	@echo "------------------------------------"
	@echo "Removing uic and rcc generated files"
	@echo "------------------------------------"
	rm -f $(COMPILED_RESOURCE_FILES)

doc:
	@echo
	@echo "------------------------------------"
	@echo "Building documentation using sphinx."
	@echo "------------------------------------"
	cd help; make html

pylint:
	@echo
	@echo "-----------------"
	@echo "Pylint violations"
	@echo "-----------------"
	@pylint --reports=n --rcfile=pylintrc . || true
	@echo
	@echo "----------------------"
	@echo "If you get a 'no module named qgis.core' error, try sourcing"
	@echo "the helper script we have provided first then run make pylint."
	@echo "e.g. source scripts/run-env-linux.sh <path to qgis install>; make pylint"
	@echo "----------------------"

# Run pep8/pycodestyle checking
pep8:
	@echo
	@echo "-----------"
	@echo "PEP8 issues"
	@echo "-----------"
	@pep8 --repeat --ignore=E203,E121,E122,E123,E124,E125,E126,E127,E128 --exclude $(PEP8EXCLUDE) . || true
	@echo "-----------"
	@echo "Ignored in PEP8 check:"
	@echo $(PEP8EXCLUDE)
