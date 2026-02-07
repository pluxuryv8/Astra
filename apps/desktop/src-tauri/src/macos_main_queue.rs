//! Helpers for running work on macOS main dispatch queue.
//!
//! Why: some system APIs used by automation libraries (e.g. keyboard layout mapping)
//! require main queue and will crash if invoked from background threads.

#[cfg(target_os = "macos")]
mod imp {
    use std::mem::MaybeUninit;
    use std::os::raw::c_void;

    type DispatchQueue = *mut c_void;

    #[link(name = "dispatch")]
    extern "C" {
        fn dispatch_get_main_queue() -> DispatchQueue;
        fn dispatch_sync_f(queue: DispatchQueue, context: *mut c_void, work: extern "C" fn(*mut c_void));
    }

    extern "C" {
        fn pthread_main_np() -> i32;
    }

    #[inline]
    fn is_main_thread() -> bool {
        // `pthread_main_np` is macOS-only.
        unsafe { pthread_main_np() != 0 }
    }

    pub fn sync<T, F>(f: F) -> std::thread::Result<T>
    where
        F: FnOnce() -> T + Send,
        T: Send,
    {
        if is_main_thread() {
            return std::panic::catch_unwind(std::panic::AssertUnwindSafe(f));
        }

        struct Ctx<F, T> {
            f: Option<F>,
            result: MaybeUninit<std::thread::Result<T>>,
        }

        extern "C" fn trampoline<F, T>(ctx: *mut c_void)
        where
            F: FnOnce() -> T + Send,
            T: Send,
        {
            // SAFETY: `ctx` points to a valid `Ctx` for the duration of `dispatch_sync_f`.
            unsafe {
                let ctx = &mut *(ctx as *mut Ctx<F, T>);
                let f = ctx.f.take().expect("macos_main_queue: closure already taken");
                let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(f));
                ctx.result.write(res);
            }
        }

        let mut ctx = Ctx {
            f: Some(f),
            result: MaybeUninit::uninit(),
        };

        // SAFETY: synchronous dispatch keeps `ctx` alive until `trampoline` completes.
        unsafe {
            dispatch_sync_f(
                dispatch_get_main_queue(),
                (&mut ctx as *mut Ctx<F, T>).cast::<c_void>(),
                trampoline::<F, T>,
            );
            ctx.result.assume_init()
        }
    }
}

#[cfg(not(target_os = "macos"))]
mod imp {
    pub fn sync<T, F>(f: F) -> std::thread::Result<T>
    where
        F: FnOnce() -> T + Send,
        T: Send,
    {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(f))
    }
}

pub use imp::sync;

