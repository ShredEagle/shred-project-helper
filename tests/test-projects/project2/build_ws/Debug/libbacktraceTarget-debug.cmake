
set(libbacktrace_INCLUDE_DIRS_DEBUG "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/include")
set(libbacktrace_INCLUDE_DIR_DEBUG "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/include")
set(libbacktrace_INCLUDES_DEBUG "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/include")
set(libbacktrace_RES_DIRS_DEBUG )
set(libbacktrace_DEFINITIONS_DEBUG )
set(libbacktrace_LINKER_FLAGS_DEBUG_LIST
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:>"
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:>"
        "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:>"
)
set(libbacktrace_COMPILE_DEFINITIONS_DEBUG )
set(libbacktrace_COMPILE_OPTIONS_DEBUG_LIST "" "")
set(libbacktrace_COMPILE_OPTIONS_C_DEBUG "")
set(libbacktrace_COMPILE_OPTIONS_CXX_DEBUG "")
set(libbacktrace_LIBRARIES_TARGETS_DEBUG "") # Will be filled later, if CMake 3
set(libbacktrace_LIBRARIES_DEBUG "") # Will be filled later
set(libbacktrace_LIBS_DEBUG "") # Same as libbacktrace_LIBRARIES
set(libbacktrace_SYSTEM_LIBS_DEBUG )
set(libbacktrace_FRAMEWORK_DIRS_DEBUG )
set(libbacktrace_FRAMEWORKS_DEBUG )
set(libbacktrace_FRAMEWORKS_FOUND_DEBUG "") # Will be filled later
set(libbacktrace_BUILD_MODULES_PATHS_DEBUG )

conan_find_apple_frameworks(libbacktrace_FRAMEWORKS_FOUND_DEBUG "${libbacktrace_FRAMEWORKS_DEBUG}" "${libbacktrace_FRAMEWORK_DIRS_DEBUG}")

mark_as_advanced(libbacktrace_INCLUDE_DIRS_DEBUG
                 libbacktrace_INCLUDE_DIR_DEBUG
                 libbacktrace_INCLUDES_DEBUG
                 libbacktrace_DEFINITIONS_DEBUG
                 libbacktrace_LINKER_FLAGS_DEBUG_LIST
                 libbacktrace_COMPILE_DEFINITIONS_DEBUG
                 libbacktrace_COMPILE_OPTIONS_DEBUG_LIST
                 libbacktrace_LIBRARIES_DEBUG
                 libbacktrace_LIBS_DEBUG
                 libbacktrace_LIBRARIES_TARGETS_DEBUG)

# Find the real .lib/.a and add them to libbacktrace_LIBS and libbacktrace_LIBRARY_LIST
set(libbacktrace_LIBRARY_LIST_DEBUG backtrace)
set(libbacktrace_LIB_DIRS_DEBUG "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/lib")

# Gather all the libraries that should be linked to the targets (do not touch existing variables):
set(_libbacktrace_DEPENDENCIES_DEBUG "${libbacktrace_FRAMEWORKS_FOUND_DEBUG} ${libbacktrace_SYSTEM_LIBS_DEBUG} ")

conan_package_library_targets("${libbacktrace_LIBRARY_LIST_DEBUG}"  # libraries
                              "${libbacktrace_LIB_DIRS_DEBUG}"      # package_libdir
                              "${_libbacktrace_DEPENDENCIES_DEBUG}"  # deps
                              libbacktrace_LIBRARIES_DEBUG            # out_libraries
                              libbacktrace_LIBRARIES_TARGETS_DEBUG    # out_libraries_targets
                              "_DEBUG"                          # build_type
                              "libbacktrace")                                      # package_name

set(libbacktrace_LIBS_DEBUG ${libbacktrace_LIBRARIES_DEBUG})

foreach(_FRAMEWORK ${libbacktrace_FRAMEWORKS_FOUND_DEBUG})
    list(APPEND libbacktrace_LIBRARIES_TARGETS_DEBUG ${_FRAMEWORK})
    list(APPEND libbacktrace_LIBRARIES_DEBUG ${_FRAMEWORK})
endforeach()

foreach(_SYSTEM_LIB ${libbacktrace_SYSTEM_LIBS_DEBUG})
    list(APPEND libbacktrace_LIBRARIES_TARGETS_DEBUG ${_SYSTEM_LIB})
    list(APPEND libbacktrace_LIBRARIES_DEBUG ${_SYSTEM_LIB})
endforeach()

# We need to add our requirements too
set(libbacktrace_LIBRARIES_TARGETS_DEBUG "${libbacktrace_LIBRARIES_TARGETS_DEBUG};")
set(libbacktrace_LIBRARIES_DEBUG "${libbacktrace_LIBRARIES_DEBUG};")

set(CMAKE_MODULE_PATH "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/" ${CMAKE_MODULE_PATH})
set(CMAKE_PREFIX_PATH "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/" ${CMAKE_PREFIX_PATH})
