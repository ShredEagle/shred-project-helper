# Cannot accept COMPONENTS arguments in a leaf cmake components.
if (${CMAKE_FIND_PACKAGE_NAME}_FIND_COMPONENTS)
    set(${CMAKE_FIND_PACKAGE_NAME}_NOT_FOUND_MESSAGE
        "The '${CMAKE_FIND_PACKAGE_NAME}' package does not accept components, \
         but it received '${${CMAKE_FIND_PACKAGE_NAME}_FIND_COMPONENTS}'")
    set(${CMAKE_FIND_PACKAGE_NAME}_FOUND False)
    return()
endif()

include(CMakeFindDependencyMacro)
# If a file to find upstream(s) for the current package is provided, it is included
# (Note: this file should have been configured from a template by cmc_install_packageconfig call).
include("${CMAKE_CURRENT_LIST_DIR}/project3FindUpstream.cmake" OPTIONAL)

# Everything that is needed to use the headers / libraries of Project3 is provided
# in the generated "export" file. This file was installed by install(EXPORT...).
include("${CMAKE_CURRENT_LIST_DIR}/project3Targets.cmake")
