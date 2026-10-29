// Test the hypothesis: the reset discards the word already in the commit pipeline.
//
// Trace evidence with CTRL=0x3 and a correct 36-byte stream (beats 8+8+8+8+4,
// TLAST only on the last): pkt_wr_ptr reached 28, not 36. Exactly one 8-byte word
// went missing, and the session check then failed on the shifted data.
//
// The commit stage is registered:
//
//     word_ready = s_wr_fire && (avail >= 8)
//     cm_valid  <= word_ready            (one cycle later)
//     ram_we     = commit_fire | tail_publish
//
// so a beat accepted in cycle N becomes a RAM write in cycle N+1 - and
// `if (!aresetn || soft_reset_pulse)` clears cm_valid, cm_word and cm_addr. A reset
// arriving in that window destroys the word in flight.
//
// The driver writes CTRL=0x3, which sets enable AND reset in one transaction, so
// the reset lands together with the first beats. That is why only the first
// transfer fails.
//
// PREDICTION: if the reset is issued BEFORE any beat arrives and allowed to
// complete, the same CTRL semantics should work. `tb_cold_start` already does
// CTRL=0x1 first and passes, which is consistent. This test adds the stronger
// case: reset first (CTRL=0x3 alone), wait for it to drain, THEN enable
// (CTRL=0x1), then stream. If that passes, the defect is an illegal reset
// sequence rather than a broken reset.

`timescale 1ns / 1ps

module tb_reset_seq;

    reg         aclk = 0;
    reg         aresetn = 0;
    always #3.0 aclk = ~aclk;

    reg  [4:0]  s_axi_awaddr  = 0;
    reg         s_axi_awvalid = 0;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata   = 0;
    reg  [3:0]  s_axi_wstrb   = 0;
    reg         s_axi_wvalid  = 0;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready  = 1;
    reg  [4:0]  s_axi_araddr  = 0;
    reg         s_axi_arvalid = 0;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready  = 1;

    reg  [63:0] s_axis_tdata  = 0;
    reg  [7:0]  s_axis_tkeep  = 0;
    reg         s_axis_tlast  = 0;
    reg         s_axis_tvalid = 0;
    wire        s_axis_tready;

    wire [7:0]  m_axis_tdata;
    wire        m_axis_tlast;
    wire        m_axis_tvalid;
    reg         m_axis_tready = 1;

    mold64_reasm #(
        .FIFO_AW (12),
        .SESSION (64'h4E41534441513031)
    ) dut (
        .aclk (aclk), .aresetn (aresetn),
        .s_axi_awaddr (s_axi_awaddr), .s_axi_awvalid (s_axi_awvalid),
        .s_axi_awready (s_axi_awready), .s_axi_wdata (s_axi_wdata),
        .s_axi_wstrb (s_axi_wstrb), .s_axi_wvalid (s_axi_wvalid),
        .s_axi_wready (s_axi_wready), .s_axi_bresp (s_axi_bresp),
        .s_axi_bvalid (s_axi_bvalid), .s_axi_bready (s_axi_bready),
        .s_axi_araddr (s_axi_araddr), .s_axi_arvalid (s_axi_arvalid),
        .s_axi_arready (s_axi_arready), .s_axi_rdata (s_axi_rdata),
        .s_axi_rresp (s_axi_rresp), .s_axi_rvalid (s_axi_rvalid),
        .s_axi_rready (s_axi_rready),
        .s_axis_tdata (s_axis_tdata), .s_axis_tkeep (s_axis_tkeep),
        .s_axis_tlast (s_axis_tlast), .s_axis_tvalid (s_axis_tvalid),
        .s_axis_tready (s_axis_tready),
        .m_axis_tdata (m_axis_tdata), .m_axis_tlast (m_axis_tlast),
        .m_axis_tvalid (m_axis_tvalid), .m_axis_tready (m_axis_tready)
    );

    localparam integer PKT_BYTES = 36;
    reg [7:0] img [0 : PKT_BYTES - 1];

    integer i, b, q, j;
    reg [63:0] wv;

    task axi_wr(input [31:0] d);
        begin
            @(negedge aclk);
            s_axi_awaddr  = 5'h18;
            s_axi_awvalid = 1;
            s_axi_wdata   = d;
            s_axi_wstrb   = 4'hF;
            s_axi_wvalid  = 1;
            @(posedge aclk);
            while (!(s_axi_awready && s_axi_wready)) @(posedge aclk);
            @(negedge aclk);
            s_axi_awvalid = 0;
            s_axi_wvalid  = 0;
        end
    endtask

    task drive_all;
        begin
            q = 0;
            @(negedge aclk);
            while (q < PKT_BYTES) begin
                wv = 64'd0;
                b  = 0;
                for (j = 0; j < 8; j = j + 1) begin
                    if (q + j < PKT_BYTES) begin
                        wv[8*j +: 8] = img[q + j];
                        b = b + 1;
                    end
                end
                s_axis_tdata  = wv;
                s_axis_tkeep  = (b == 8) ? 8'hFF : ((8'hFF >> (8 - b)));
                s_axis_tlast  = ((q + b) >= PKT_BYTES);
                s_axis_tvalid = 1'b1;
                @(posedge aclk);
                while (!s_axis_tready) @(posedge aclk);
                @(negedge aclk);
                q = q + b;
            end
            s_axis_tvalid = 1'b0;
            s_axis_tkeep  = 8'h00;
            s_axis_tlast  = 1'b0;
        end
    endtask

    initial begin
        img[0] = 8'h4E; img[1] = 8'h41; img[2] = 8'h53; img[3] = 8'h44;
        img[4] = 8'h41; img[5] = 8'h51; img[6] = 8'h30; img[7] = 8'h31;
        img[8] = 8'h00; img[9] = 8'h00;
        img[10] = 8'h00; img[11] = 8'h02;
        for (i = 0; i < 2; i = i + 1) begin
            b = 12 + i*12;
            img[b+0] = 8'h00; img[b+1] = 8'h0A;
            img[b+2] = 8'h41;
            img[b+3] = 8'h00; img[b+4] = 8'h00; img[b+5] = 8'h00;
            img[b+6] = 8'h01; img[b+7] = 8'h00; img[b+8] = 8'h00;
            img[b+9] = 8'h02; img[b+10] = 8'h00; img[b+11] = 8'h03;
        end

        aresetn = 0;
        repeat (20) @(posedge aclk);
        aresetn = 1;
        repeat (10) @(posedge aclk);

        // SERIALISED: reset+enable, let it drain, then enable only.
        axi_wr(32'h3);
        repeat (10) @(posedge aclk);
        axi_wr(32'h1);
        repeat (10) @(posedge aclk);

        drive_all;
        repeat (400) @(posedge aclk);

        $display("RESETSEQ pkts=%0d msgs=%0d err=%0d",
                 dut.rx_packets, dut.rx_messages, dut.error_count);
        if (dut.rx_packets == 1 && dut.rx_messages == 2 && dut.error_count == 0)
            $display("RESETSEQ-PASS");
        else
            $display("RESETSEQ-FAIL");
        $finish;
    end

endmodule
