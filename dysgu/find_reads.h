#include <cstdint>
#include <iostream>
#include <functional>
#include <string>
#include <utility>
#include <queue>
#include <map>

#include "robin_hood.h"
#include "./htslib/htslib/sam.h"
#include "./htslib/htslib/hfile.h"
#include "xxhash64.h"


int search_hts_alignments(char* infile, char* outfile, uint32_t min_within_size, int clip_length,
                          int threads) {

    const int check_clips = (clip_length > 0) ? 1 : 0;

    int result;
    htsFile *fp_in = hts_open(infile, "r");

    if (threads > 1) {  // set additional threads beyond main thread
        result = hts_set_threads(fp_in, threads - 1);
        if (result != 0) { return -1; }
    }

    bam_hdr_t* samHdr = sam_hdr_read(fp_in);  // read header

    if (!samHdr) { return -1;}

    htsFile *f_out = hts_open(outfile, "wb0");
    result = hts_set_threads(f_out, 1);
        if (result != 0) { return -1; }

    result = sam_hdr_write(f_out, samHdr);
    if (result != 0) { return -1; }

    int max_scope = 100000;
    int max_write_queue = 500000;

    uint64_t total = 0;

    std::pair<uint64_t, bam1_t*> scope_item;
    std::deque<std::pair<uint64_t, bam1_t*>> scope;
    std::vector<bam1_t*> write_queue;  // Write in blocks
    robin_hood::unordered_set<uint64_t> read_names;
    // Initialize first item in scope, set hash once read has been read
    scope.push_back(std::make_pair(0, bam_init1()));

    // Read alignment into the back of scope queue
    while (sam_read1(fp_in, samHdr, scope.back().second) >= 0) {

        if (scope.size() > max_scope) {
            scope_item = scope[0];

            if (read_names.find(scope_item.first) != read_names.end()) {
                write_queue.push_back(scope_item.second);
            } else {
                bam_destroy1(scope_item.second);
            }
            scope.pop_front();
        }

        // Check if write queue is full
        if (write_queue.size() > max_write_queue) {
            for (const auto& val: write_queue) {
                result = sam_write1(f_out, samHdr, val);
                if (result < 0) { return -1; }
                total += 1;
                bam_destroy1(val);
            }
            write_queue.clear();
        }

        // Add hash to current alignment
        bam1_t* aln = scope.back().second;

        const uint16_t flag = aln->core.flag;
        // Process current alignment. Skip if duplicate or unmapped
        if (flag & 1028 || aln->core.n_cigar == 0 || aln->core.l_qname == 0) { continue; }

        const uint64_t precalculated_hash = XXHash64::hash(bam_get_qname(aln), aln->core.l_qname, 0);
        scope.back().first = precalculated_hash;

        // Add a new item to the queue for next iteration
        scope.push_back(std::make_pair(0, bam_init1()));

        if (read_names.find(precalculated_hash) == read_names.end()) {

            // Check for discordant of supplementary
            if ((~flag & 2 && flag & 1) || flag & 2048) {
                read_names.insert(precalculated_hash);

                continue;
            }
            // Check for SA tag
            if (bam_aux_get(aln, "SA")) {
                read_names.insert(precalculated_hash);
                continue;
            }

            const uint32_t* cigar = bam_get_cigar(aln);

            // Check cigar
            for (uint32_t k=0; k < aln->core.n_cigar; k++) {

                uint32_t op = bam_cigar_op(cigar[k]);
                uint32_t length = bam_cigar_oplen(cigar[k]);

                if ((check_clips) && (op == BAM_CSOFT_CLIP ) && (length >= clip_length)) {  // || op == BAM_CHARD_CLIP
                    read_names.insert(precalculated_hash);

                    break;
                }

                if ((op == BAM_CINS || op == BAM_CDEL) && (length >= min_within_size)) {
                    read_names.insert(precalculated_hash);
                    break;
                }
            }
        }
    }

    while (scope.size() > 0) {
        scope_item = scope[0];
        if (read_names.find(scope_item.first) != read_names.end()) {
            write_queue.push_back(scope_item.second);
        } else {
            bam_destroy1(scope_item.second);
        }
        scope.pop_front();
    }

    for (const auto& val: write_queue) {
        result = sam_write1(f_out, samHdr, val);
        if (result < 0) { return -1; }
        total += 1;
        bam_destroy1(val);
    }

    result = hts_close(fp_in);
    if (result != 0) { return -1; };

    result = hts_close(f_out);
    if (result < 0) { return -1; };

    f_out = NULL;

    return total;

}