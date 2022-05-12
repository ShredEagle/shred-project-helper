
if(NOT TARGET project3::project3)
    add_library(project3::project3 INTERFACE IMPORTED)
endif()

# Load the debug and release library finders
get_filename_component(_DIR "${CMAKE_CURRENT_LIST_FILE}" PATH)
file(GLOB CONFIG_FILES "${_DIR}/project3Target-*.cmake")

foreach(f ${CONFIG_FILES})
    include(${f})
endforeach()
