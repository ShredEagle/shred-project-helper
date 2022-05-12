
set(project3_INCLUDE_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project3/conan/include")
set(project3_INCLUDE_DIR_DEBUG "/home/franz/sph/tests/test-projects/project3/conan/include")
set(project3_INCLUDES_DEBUG "/home/franz/sph/tests/test-projects/project3/conan/include")
set(project3_RES_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project3/conan/res")
set(project3_DEFINITIONS_DEBUG )
set(project3_LINKER_FLAGS_DEBUG_LIST
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:>"
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:>"
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:>"
)
set(project3_COMPILE_DEFINITIONS_DEBUG )
set(project3_COMPILE_OPTIONS_DEBUG_LIST "" "")
set(project3_COMPILE_OPTIONS_C_DEBUG "")
set(project3_COMPILE_OPTIONS_CXX_DEBUG "")
set(project3_LIBRARIES_TARGETS_DEBUG "") # Will be filled later, if CMake 3
set(project3_LIBRARIES_DEBUG "") # Will be filled later
set(project3_LIBS_DEBUG "") # Same as project3_LIBRARIES
set(project3_SYSTEM_LIBS_DEBUG )
set(project3_FRAMEWORK_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project3/conan/Frameworks")
set(project3_FRAMEWORKS_DEBUG )
set(project3_FRAMEWORKS_FOUND_DEBUG "") # Will be filled later
set(project3_BUILD_MODULES_PATHS_DEBUG )

conan_find_apple_frameworks(project3_FRAMEWORKS_FOUND_DEBUG "${project3_FRAMEWORKS_DEBUG}" "${project3_FRAMEWORK_DIRS_DEBUG}")

mark_as_advanced(project3_INCLUDE_DIRS_DEBUG
                 project3_INCLUDE_DIR_DEBUG
                 project3_INCLUDES_DEBUG
                 project3_DEFINITIONS_DEBUG
                 project3_LINKER_FLAGS_DEBUG_LIST
                 project3_COMPILE_DEFINITIONS_DEBUG
                 project3_COMPILE_OPTIONS_DEBUG_LIST
                 project3_LIBRARIES_DEBUG
                 project3_LIBS_DEBUG
                 project3_LIBRARIES_TARGETS_DEBUG)

# Find the real .lib/.a and add them to project3_LIBS and project3_LIBRARY_LIST
set(project3_LIBRARY_LIST_DEBUG )
set(project3_LIB_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project3/conan/lib")

# Gather all the libraries that should be linked to the targets (do not touch existing variables):
set(_project3_DEPENDENCIES_DEBUG "${project3_FRAMEWORKS_FOUND_DEBUG} ${project3_SYSTEM_LIBS_DEBUG} Boost::Boost")

conan_package_library_targets("${project3_LIBRARY_LIST_DEBUG}"  # libraries
                              "${project3_LIB_DIRS_DEBUG}"      # package_libdir
                              "${_project3_DEPENDENCIES_DEBUG}"  # deps
                              project3_LIBRARIES_DEBUG            # out_libraries
                              project3_LIBRARIES_TARGETS_DEBUG    # out_libraries_targets
                              "_DEBUG"                          # build_type
                              "project3")                                      # package_name

set(project3_LIBS_DEBUG ${project3_LIBRARIES_DEBUG})

foreach(_FRAMEWORK ${project3_FRAMEWORKS_FOUND_DEBUG})
    list(APPEND project3_LIBRARIES_TARGETS_DEBUG ${_FRAMEWORK})
    list(APPEND project3_LIBRARIES_DEBUG ${_FRAMEWORK})
endforeach()

foreach(_SYSTEM_LIB ${project3_SYSTEM_LIBS_DEBUG})
    list(APPEND project3_LIBRARIES_TARGETS_DEBUG ${_SYSTEM_LIB})
    list(APPEND project3_LIBRARIES_DEBUG ${_SYSTEM_LIB})
endforeach()

# We need to add our requirements too
set(project3_LIBRARIES_TARGETS_DEBUG "${project3_LIBRARIES_TARGETS_DEBUG};Boost::Boost")
set(project3_LIBRARIES_DEBUG "${project3_LIBRARIES_DEBUG};Boost::Boost")

set(CMAKE_MODULE_PATH "/home/franz/sph/tests/test-projects/project3/conan/" ${CMAKE_MODULE_PATH})
set(CMAKE_PREFIX_PATH "/home/franz/sph/tests/test-projects/project3/conan/" ${CMAKE_PREFIX_PATH})
