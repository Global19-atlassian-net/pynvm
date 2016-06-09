from cffi import FFI
ffi = FFI()

ffi.set_source("_pmem",
               """
                   #include <libpmem.h>
                   #include <libpmemlog.h>
                   #include <libpmemblk.h>
                   #include <libpmemobj.h>
               """,
               libraries=['pmem', 'pmemlog', 'pmemblk', 'pmemobj'])

ffi.cdef("""
    /* libpmem */
    typedef int mode_t;

    const char *pmem_errormsg(void);
    void *pmem_map_file(const char *path, size_t len, int flags, mode_t mode,
        size_t *mapped_lenp, int *is_pmemp);
    int pmem_unmap(void *addr, size_t len);
    int pmem_has_hw_drain(void);
    int pmem_is_pmem(void *addr, size_t len);
    const char *pmem_check_version(
        unsigned major_required,
        unsigned minor_required);
    void pmem_persist(void *addr, size_t len);
    int pmem_msync(void *addr, size_t len);
    void pmem_flush(void *addr, size_t len);
    void pmem_drain(void);

    /* libpmemlog */
    typedef struct pmemlog PMEMlogpool;
    typedef int off_t;

    const char *pmemlog_errormsg(void);
    PMEMlogpool *pmemlog_open(const char *path);
    PMEMlogpool *pmemlog_create(const char *path, size_t poolsize, mode_t mode);
    void pmemlog_close(PMEMlogpool *plp);
    size_t pmemlog_nbyte(PMEMlogpool *plp);
    void pmemlog_rewind(PMEMlogpool *plp);
    off_t pmemlog_tell(PMEMlogpool *plp);
    int pmemlog_check(const char *path);
    int pmemlog_append(PMEMlogpool *plp, const void *buf, size_t count);
    const char *pmemlog_check_version(
        unsigned major_required,
        unsigned minor_required);
    void pmemlog_walk(PMEMlogpool *plp, size_t chunksize,
        int (*process_chunk)(const void *buf, size_t len, void *arg),
        void *arg);

    /* libpmemblk */
    typedef struct pmemblk PMEMblkpool;
    const char *pmemblk_errormsg(void);
    PMEMblkpool *pmemblk_open(const char *path, size_t bsize);
    PMEMblkpool *pmemblk_create(const char *path, size_t bsize,
        size_t poolsize, mode_t mode);
    void pmemblk_close(PMEMblkpool *pbp);
    int pmemblk_check(const char *path, size_t bsize);
    size_t pmemblk_bsize(PMEMblkpool *pbp);
    size_t pmemblk_nblock(PMEMblkpool *pbp);
    int pmemblk_read(PMEMblkpool *pbp, void *buf, off_t blockno);
    int pmemblk_write(PMEMblkpool *pbp, const void *buf, off_t blockno);
    int pmemblk_set_zero(PMEMblkpool *pbp, off_t blockno);
    int pmemblk_set_error(PMEMblkpool *pbp, off_t blockno);
    const char *pmemblk_check_version(
        unsigned major_required,
        unsigned minor_required);

    /* libpmemobj */
    typedef struct pmemobjpool PMEMobjpool;
    #define PMEMOBJ_MIN_POOL ...
    #define PMEMOBJ_MAX_ALLOC_SIZE ...

    const char *pmemobj_errormsg(void);
    PMEMobjpool *pmemobj_open(const char *path, const char *layout);
    PMEMobjpool *pmemobj_create(const char *path, const char *layout,
        size_t poolsize, mode_t mode);
    void pmemobj_close(PMEMobjpool *pop);
    int pmemobj_check(const char *path, const char *layout);

""")

if __name__ == "__main__":
    ffi.compile()
