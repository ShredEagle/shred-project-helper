#pragma once

#if defined(_WIN32)

#include <windows.h>
#include <wincon.h>

#endif


namespace ad {
namespace grapito {
namespace windows {


#if defined(_WIN32)

/// \brief Attach the parent console if present, or allocate a new console.
void attachOutputToConsole()
{
    if(AttachConsole(ATTACH_PARENT_PROCESS) || AllocConsole())
    {
        freopen("CONOUT$", "w", stdout);
        freopen("CONOUT$", "w", stderr);
    }
}

#else

void attachOutputToConsole()
{}

#endif


} // namespace windows
} // namespace grapito
} // namespace ad
