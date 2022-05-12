
set(project2_INCLUDE_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project2/conan/include")
set(project2_INCLUDE_DIR_DEBUG "/home/franz/sph/tests/test-projects/project2/conan/include")
set(project2_INCLUDES_DEBUG "/home/franz/sph/tests/test-projects/project2/conan/include")
set(project2_RES_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project2/conan/res")
set(project2_DEFINITIONS_DEBUG )
set(project2_LINKER_FLAGS_DEBUG_LIST
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:>"
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:>"
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:>"
)
set(project2_COMPILE_DEFINITIONS_DEBUG )
set(project2_COMPILE_OPTIONS_DEBUG_LIST "" "")
set(project2_COMPILE_OPTIONS_C_DEBUG "")
set(project2_COMPILE_OPTIONS_CXX_DEBUG "")
set(project2_LIBRARIES_TARGETS_DEBUG "") # Will be filled later, if CMake 3
set(project2_LIBRARIES_DEBUG "") # Will be filled later
set(project2_LIBS_DEBUG "") # Same as project2_LIBRARIES
set(project2_SYSTEM_LIBS_DEBUG )
set(project2_FRAMEWORK_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project2/conan/Frameworks")
set(project2_FRAMEWORKS_DEBUG )
set(project2_FRAMEWORKS_FOUND_DEBUG "") # Will be filled later
set(project2_BUILD_MODULES_PATHS_DEBUG )

conan_find_apple_frameworks(project2_FRAMEWORKS_FOUND_DEBUG "${project2_FRAMEWORKS_DEBUG}" "${project2_FRAMEWORK_DIRS_DEBUG}")

mark_as_advanced(project2_INCLUDE_DIRS_DEBUG
                 project2_INCLUDE_DIR_DEBUG
                 project2_INCLUDES_DEBUG
                 project2_DEFINITIONS_DEBUG
                 project2_LINKER_FLAGS_DEBUG_LIST
                 project2_COMPILE_DEFINITIONS_DEBUG
                 project2_COMPILE_OPTIONS_DEBUG_LIST
                 project2_LIBRARIES_DEBUG
                 project2_LIBS_DEBUG
                 project2_LIBRARIES_TARGETS_DEBUG)

# Find the real .lib/.a and add them to project2_LIBS and project2_LIBRARY_LIST
set(project2_LIBRARY_LIST_DEBUG )
set(project2_LIB_DIRS_DEBUG "/home/franz/sph/tests/test-projects/project2/conan/lib")

# Gather all the libraries that should be linked to the targets (do not touch existing variables):
set(_project2_DEPENDENCIES_DEBUG "${project2_FRAMEWORKS_FOUND_DEBUG} ${project2_SYSTEM_LIBS_DEBUG} Boost::Boost;project3::project3")

conan_package_library_targets("${project2_LIBRARY_LIST_DEBUG}"  # libraries
                              "${project2_LIB_DIRS_DEBUG}"      # package_libdir
                              "${_project2_DEPENDENCIES_DEBUG}"  # deps
                              project2_LIBRARIES_DEBUG            # out_libraries
                              project2_LIBRARIES_TARGETS_DEBUG    # out_libraries_targets
                              "_DEBUG"                          # build_type
                              "project2")                                      # package_name

set(project2_LIBS_DEBUG ${project2_LIBRARIES_DEBUG})

foreach(_FRAMEWORK ${project2_FRAMEWORKS_FOUND_DEBUG})
    list(APPEND project2_LIBRARIES_TARGETS_DEBUG ${_FRAMEWORK})
    list(APPEND project2_LIBRARIES_DEBUG ${_FRAMEWORK})
endforeach()

foreach(_SYSTEM_LIB ${project2_SYSTEM_LIBS_DEBUG})
    list(APPEND project2_LIBRARIES_TARGETS_DEBUG ${_SYSTEM_LIB})
    list(APPEND project2_LIBRARIES_DEBUG ${_SYSTEM_LIB})
endforeach()

# We need to add our requirements too
set(project2_LIBRARIES_TARGETS_DEBUG "${project2_LIBRARIES_TARGETS_DEBUG};Boost::Boost;project3::project3")
set(project2_LIBRARIES_DEBUG "${project2_LIBRARIES_DEBUG};Boost::Boost;project3::project3")

set(CMAKE_MODULE_PATH "/home/franz/sph/tests/test-projects/project2/conan/" ${CMAKE_MODULE_PATH})
set(CMAKE_PREFIX_PATH "/home/franz/sph/tests/test-projects/project2/conan/" ${CMAKE_PREFIX_PATH})
